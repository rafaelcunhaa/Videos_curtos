#!/usr/bin/env python3
"""
=======================================================
  SERVIDOR LOCAL — BoomVibes Dashboard
=======================================================
  API FastAPI que conecta a interface.html aos scripts
  Python reais do sistema.

  Inicie:
    python servidor.py

  Acesse:
    http://localhost:8000

  A interface.html se conecta automaticamente a este
  servidor via fetch() para executar as operações reais.
=======================================================
"""

import asyncio
import importlib
import json
import re
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    StreamingResponse,
)
from pydantic import BaseModel

# Setup de paths
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import banco
from constantes import EXTENSOES_VIDEO_VALIDAS, MAX_LOGS_BUFFER, TAXA_CAMBIO_USD_BRL
from logger_setup import get_logger

logger = get_logger(__name__)

# ── Estado global do servidor ──────────────────────────
_estado = {
    "daemon_ativo": False,
    "daemon_task": None,
    "processando": False,
    "logs_buffer": [],  # buffer de logs para SSE
    "ultimo_pipeline": None,
}

# ── Rate Limiting Simples ──────────────────────────────
# Rastreia requisições por IP para prevenir abuso
_rate_limit_store = defaultdict(list)


def check_rate_limit(request: Request, max_requests: int, window_seconds: int):
    """
    Verifica se o cliente excedeu o limite de requisições.

    Args:
        request: Request do FastAPI
        max_requests: Número máximo de requisições permitidas
        window_seconds: Janela de tempo em segundos

    Raises:
        HTTPException(429): Se limite for excedido
    """
    client_ip = request.client.host if request.client else "unknown"
    agora = datetime.now()

    # Limpar requisições antigas da janela
    janela_inicio = agora - timedelta(seconds=window_seconds)
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if ts > janela_inicio
    ]

    # Verificar limite
    if len(_rate_limit_store[client_ip]) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {max_requests} requisições por {window_seconds}s excedido. Tente novamente em alguns segundos.",
        )

    # Registrar esta requisição
    _rate_limit_store[client_ip].append(agora)


def secure_path(*parts: str) -> Path:
    """
    Constrói um caminho seguro dentro de BASE_DIR, impedindo path traversal.
    Remove '..' e componentes absolutos de cada parte.
    """
    base = BASE_DIR.resolve()
    caminho = base
    for p in parts:
        nome = Path(str(p)).name  # descarta diretórios e '..'
        caminho = caminho / nome
    if not str(caminho.resolve()).startswith(str(base)):
        raise ValueError(f"Caminho fora do diretório permitido: {caminho}")
    return caminho


MAX_LOGS_BUFFER = 500


# ── App ───────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BoomVibes servidor iniciado em http://localhost:8000")
    yield
    if _estado["daemon_task"]:
        _estado["daemon_task"].cancel()
    logger.info("Servidor encerrado")


app = FastAPI(
    title="BoomVibes API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Servir interface.html ─────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve a interface principal."""
    html_path = BASE_DIR / "interface.html"
    if not html_path.exists():
        raise HTTPException(404, "interface.html não encontrado")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ── SSE — logs em tempo real ─────────────────────────


def _push_log(msg: str, tipo: str = "info"):
    """Adiciona log ao buffer SSE."""
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "msg": msg,
        "tipo": tipo,
    }
    _estado["logs_buffer"].append(entry)
    if len(_estado["logs_buffer"]) > MAX_LOGS_BUFFER:
        _estado["logs_buffer"].pop(0)


@app.get("/api/logs/stream")
async def logs_stream():
    """
    Server-Sent Events — envia logs em tempo real para a interface.
    A interface conecta via: new EventSource('/api/logs/stream')
    """

    async def gerador() -> AsyncGenerator[str, None]:
        ultimo_idx = len(_estado["logs_buffer"])
        while True:
            novos = _estado["logs_buffer"][ultimo_idx:]
            for entry in novos:
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            ultimo_idx = len(_estado["logs_buffer"])
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gerador(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Banco — stats ────────────────────────────────────


@app.get("/api/stats")
async def get_stats():
    """Retorna estatísticas gerais do banco."""
    try:
        banco.inicializar()
        s = banco.stats()
        custo_brl = s.get("custo_total_usd", 0) * TAXA_CAMBIO_USD_BRL
        return {
            "total_videos": s.get("total_videos", 0),
            "total_cortes": s.get("total_cortes", 0),
            "prontos": s.get("prontos", 0),
            "agendados": s.get("agendados", 0),
            "postados": s.get("postados", 0),
            "erros": s.get("erros", 0),
            "custo_total_usd": s.get("custo_total_usd", 0),
            "custo_brl": round(custo_brl, 2),
        }
    except Exception as e:
        logger.error("Erro ao buscar stats: %s", e)
        return {
            "total_videos": 0,
            "total_cortes": 0,
            "prontos": 0,
            "agendados": 0,
            "postados": 0,
            "erros": 0,
            "custo_total_usd": 0,
            "custo_brl": 0,
        }


@app.get("/api/cortes")
async def get_cortes(status: Optional[str] = None, limit: int = 50):
    """Lista cortes do banco com filtro opcional por status."""
    try:
        banco.inicializar()
        cortes = banco.listar_cortes(status=status)[:limit]
        return {"cortes": cortes, "total": len(cortes)}
    except Exception as e:
        logger.error("Erro ao listar cortes: %s", e)
        return {"cortes": [], "total": 0}


@app.get("/api/videos")
async def get_videos(limit: int = 50):
    """Lista vídeos do banco."""
    try:
        banco.inicializar()
        videos = banco.listar_videos()[:limit]
        return {"videos": videos, "total": len(videos)}
    except Exception as e:
        logger.error("Erro ao listar vídeos: %s", e)
        return {"videos": [], "total": 0}


@app.get("/api/fila/proximas")
async def get_proximas_postagens():
    """Retorna próximas postagens agendadas."""
    try:
        banco.inicializar()
        agendados = banco.listar_cortes(status="agendado")
        # Ordenar por agendado_para
        agendados.sort(key=lambda x: x.get("agendado_para", "") or "")
        return {"agendados": agendados[:10]}
    except Exception as e:
        logger.error("Erro ao buscar fila: %s", e)
        return {"agendados": []}


# ── Gerar conteúdo ───────────────────────────────────


class GerarRequest(BaseModel):
    formatos: list[str] = ["reflexao", "historia", "versiculo"]
    tema: Optional[str] = None
    quantidade: Optional[int] = None


@app.post("/api/gerar")
async def gerar_conteudo(req: GerarRequest, bg: BackgroundTasks, request: Request):
    """Gera vídeos originais em background e envia logs via SSE."""
    # Rate limit: máximo 5 gerações por hora (custa API)
    check_rate_limit(request, max_requests=5, window_seconds=3600)

    if _estado["processando"]:
        raise HTTPException(409, "Já há um processo em execução")

    bg.add_task(_task_gerar, req.formatos, req.tema, req.quantidade)
    return {"status": "iniciado", "formatos": req.formatos}


async def _task_gerar(formatos: list, tema: Optional[str], quantidade: Optional[int]):
    _estado["processando"] = True
    try:
        _push_log(f"→ Gerando {len(formatos)} vídeo(s)...", "info")

        # Rodar em processo separado para não bloquear o servidor
        args = [sys.executable, str(BASE_DIR / "gerador_conteudo.py")]
        if tema:
            args += ["--tema", tema]
        if quantidade:
            args += ["--quantidade", str(quantidade)]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )

        async for linha in proc.stdout:
            txt = linha.decode("utf-8", errors="replace").strip()
            if txt:
                tipo = (
                    "ok"
                    if "✅" in txt or "✓" in txt
                    else (
                        "err"
                        if "✗" in txt or "Erro" in txt
                        else "ia" if "🤖" in txt else "info"
                    )
                )
                _push_log(txt, tipo)

        await proc.wait()
        if proc.returncode == 0:
            _push_log("✅ Geração concluída com sucesso!", "ok")
        else:
            _push_log("✗ Erro na geração — verifique o log", "err")

    except Exception as e:
        _push_log(f"✗ Erro inesperado: {e}", "err")
        logger.error("Erro na task de geração: %s", e, exc_info=True)
    finally:
        _estado["processando"] = False


# ── Pipeline diário ──────────────────────────────────


@app.post("/api/pipeline/rodar")
async def rodar_pipeline(bg: BackgroundTasks):
    """Roda o pipeline diário completo em background."""
    if _estado["processando"]:
        raise HTTPException(409, "Já há um processo em execução")
    bg.add_task(_task_pipeline)
    return {"status": "iniciado"}


async def _task_pipeline():
    _estado["processando"] = True
    _estado["ultimo_pipeline"] = datetime.now().isoformat()
    try:
        _push_log("→ Iniciando pipeline diário completo...", "info")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(BASE_DIR / "run_diario.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )
        async for linha in proc.stdout:
            txt = linha.decode("utf-8", errors="replace").strip()
            if txt:
                tipo = (
                    "ok"
                    if "✅" in txt or "✓" in txt
                    else (
                        "err"
                        if "✗" in txt
                        else "ia" if "🤖" in txt else "warn" if "⚠" in txt else "info"
                    )
                )
                _push_log(txt, tipo)
        await proc.wait()
        rc = proc.returncode
        _push_log(
            "✅ Pipeline concluído!" if rc == 0 else "✗ Pipeline com erros",
            "ok" if rc == 0 else "err",
        )
    except Exception as e:
        _push_log(f"✗ Erro: {e}", "err")
        logger.error("Erro na task de pipeline: %s", e, exc_info=True)
    finally:
        _estado["processando"] = False


@app.get("/api/pipeline/status")
async def pipeline_status():
    return {
        "processando": _estado["processando"],
        "ultimo_pipeline": _estado["ultimo_pipeline"],
        "daemon_ativo": _estado["daemon_ativo"],
    }


# ── YouTube → Shorts ─────────────────────────────────


class YouTubeRequest(BaseModel):
    url: str
    modelo: str = "base"
    forcar: bool = False


@app.post("/api/youtube/processar")
async def processar_youtube(req: YouTubeRequest, bg: BackgroundTasks, request: Request):
    """Baixa e processa um vídeo do YouTube em background."""
    # Rate limit: máximo 10 vídeos por hora (custa API + bandwidth)
    check_rate_limit(request, max_requests=10, window_seconds=3600)

    if _estado["processando"]:
        raise HTTPException(409, "Já há um processo em execução")

    # Validação melhorada de URL do YouTube
    import re

    YOUTUBE_REGEX = r"^https?://(www\.)?(youtube\.com|youtu\.be)/.+"
    if not re.match(YOUTUBE_REGEX, req.url):
        raise HTTPException(
            400, "URL inválida. Deve ser do YouTube (youtube.com ou youtu.be)"
        )

    bg.add_task(_task_youtube, req.url, req.modelo, req.forcar)
    return {"status": "iniciado", "url": req.url}


async def _task_youtube(url: str, modelo: str, forcar: bool):
    _estado["processando"] = True
    try:
        _push_log(f"→ Processando: {url}", "info")
        args = [
            sys.executable,
            str(BASE_DIR / "youtube_para_shorts.py"),
            "--url",
            url,
            "--modelo",
            modelo,
        ]
        if forcar:
            args.append("--forcar")
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )
        async for linha in proc.stdout:
            txt = linha.decode("utf-8", errors="replace").strip()
            if txt:
                tipo = (
                    "ok"
                    if "✅" in txt or "✓" in txt
                    else "err" if "✗" in txt else "ia" if "🤖" in txt else "info"
                )
                _push_log(txt, tipo)
        await proc.wait()
        rc = proc.returncode
        _push_log(
            "✅ Shorts gerados com sucesso!" if rc == 0 else "✗ Erro no processamento",
            "ok" if rc == 0 else "err",
        )
    except Exception as e:
        _push_log(f"✗ Erro: {e}", "err")
    finally:
        _estado["processando"] = False


# ── Vídeo local ──────────────────────────────────────


@app.post("/api/local/processar")
async def processar_local(
    request: Request, bg: BackgroundTasks, arquivo: UploadFile = File(...)
):
    """Recebe upload de vídeo e processa em background."""
    if _estado["processando"]:
        raise HTTPException(409, "Já há um processo em execução")

    # Validar extensão de arquivo
    filename = arquivo.filename or "video.mp4"
    ext = Path(filename).suffix.lower()

    if ext not in EXTENSOES_VIDEO_VALIDAS:
        raise HTTPException(
            400, f"Extensão não permitida. Use: {', '.join(EXTENSOES_VIDEO_VALIDAS)}"
        )

    # Sanitizar nome do arquivo (prevenir path traversal)
    nome_seguro = Path(filename).name  # remove qualquer path, mantém só o nome
    timestamp = datetime.now().strftime("%H%M%S")

    # Salvar arquivo temporário com nome seguro
    tmp_path = secure_path("downloads", f"upload_{timestamp}_{nome_seguro}")
    tmp_path.parent.mkdir(exist_ok=True)

    conteudo = await arquivo.read()
    tmp_path.write_bytes(conteudo)
    _push_log(
        f"→ Arquivo recebido: {arquivo.filename} ({len(conteudo)/1024/1024:.1f}MB)",
        "info",
    )

    bg.add_task(_task_local, str(tmp_path))
    return {"status": "iniciado", "arquivo": arquivo.filename}


async def _task_local(caminho: str):
    _estado["processando"] = True
    try:
        _push_log(f"→ Processando: {Path(caminho).name}", "info")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(BASE_DIR / "processar_video.py"),
            "--arquivo",
            caminho,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )
        async for linha in proc.stdout:
            txt = linha.decode("utf-8", errors="replace").strip()
            if txt:
                tipo = (
                    "ok"
                    if "✅" in txt or "✓" in txt
                    else "err" if "✗" in txt else "ia" if "🤖" in txt else "info"
                )
                _push_log(txt, tipo)
        await proc.wait()
        rc = proc.returncode
        _push_log(
            "✅ Vídeo processado!" if rc == 0 else "✗ Erro no processamento",
            "ok" if rc == 0 else "err",
        )
    except Exception as e:
        _push_log(f"✗ Erro: {e}", "err")
    finally:
        _estado["processando"] = False


# ── Agendador ────────────────────────────────────────


@app.post("/api/agendar/lote")
async def agendar_lote(bg: BackgroundTasks):
    """Agenda todos os cortes prontos automaticamente."""
    bg.add_task(_task_agendar_lote)
    return {"status": "iniciado"}


async def _task_agendar_lote():
    try:
        _push_log("→ Agendando vídeos prontos...", "info")
        from agendador import agendar_lote

        banco.inicializar()
        # Rodar em thread para não bloquear event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, agendar_lote)
        _push_log("✅ Vídeos agendados nos melhores horários!", "ok")
    except Exception as e:
        _push_log(f"✗ Erro ao agendar: {e}", "err")
        logger.error("Erro ao agendar lote: %s", e, exc_info=True)


@app.post("/api/agendar/corte/{corte_id}")
async def agendar_corte(corte_id: int, data_hora: Optional[str] = None):
    """Agenda um corte específico."""
    try:
        banco.inicializar()
        from agendador import agendar_corte_automatico

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, agendar_corte_automatico, corte_id, data_hora)
        return {"status": "agendado", "corte_id": corte_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/postar/agora/{corte_id}")
async def postar_agora(corte_id: int, bg: BackgroundTasks):
    """Posta um corte imediatamente."""
    bg.add_task(_task_postar_agora, corte_id)
    return {"status": "iniciado", "corte_id": corte_id}


async def _task_postar_agora(corte_id: int):
    try:
        _push_log(f"→ Postando corte {corte_id}...", "info")
        from agendador import postar_agora

        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, postar_agora, corte_id)
        if ok:
            _push_log(f"✅ Corte {corte_id} postado com sucesso!", "ok")
        else:
            _push_log(f"✗ Falha ao postar corte {corte_id}", "err")
    except Exception as e:
        _push_log(f"✗ Erro: {e}", "err")


# ── Daemon ───────────────────────────────────────────


@app.post("/api/daemon/iniciar")
async def iniciar_daemon():
    """Inicia o loop de postagem automática."""
    if _estado["daemon_ativo"]:
        return {"status": "ja_ativo"}

    _estado["daemon_ativo"] = True

    async def _loop_daemon():
        _push_log("→ Daemon iniciado — verificando fila a cada 5 min", "ok")
        while _estado["daemon_ativo"]:
            try:
                banco.inicializar()
                from agendador import verificar_e_postar_agendados

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, verificar_e_postar_agendados)
            except Exception as e:
                _push_log(f"⚠ Daemon erro: {e}", "warn")
            await asyncio.sleep(300)  # 5 minutos
        _push_log("⚠ Daemon encerrado", "warn")

    _estado["daemon_task"] = asyncio.create_task(_loop_daemon())
    return {"status": "iniciado"}


@app.post("/api/daemon/parar")
async def parar_daemon():
    """Para o daemon de postagem."""
    _estado["daemon_ativo"] = False
    if _estado["daemon_task"]:
        _estado["daemon_task"].cancel()
        _estado["daemon_task"] = None
    return {"status": "parado"}


@app.get("/api/daemon/status")
async def daemon_status():
    return {"ativo": _estado["daemon_ativo"]}


# ── Analytics ────────────────────────────────────────


@app.post("/api/analytics/coletar")
async def coletar_metricas(bg: BackgroundTasks, dias: int = 28):
    """Coleta métricas do YouTube Analytics em background."""
    bg.add_task(_task_coletar, dias)
    return {"status": "iniciado", "dias": dias}


async def _task_coletar(dias: int):
    try:
        _push_log(f"→ Coletando métricas dos últimos {dias} dias...", "info")
        from analytics import coletar_metricas

        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, coletar_metricas, dias)
        _push_log(
            f"✅ Coletados: {resultado['coletados']} | "
            f"Sem dados: {resultado['sem_dados']} | "
            f"Erros: {resultado['erros']}",
            "ok",
        )
    except Exception as e:
        _push_log(f"✗ Erro na coleta: {e}", "err")
        logger.error("Erro na coleta de métricas: %s", e, exc_info=True)


@app.post("/api/analytics/analisar")
async def analisar_performance(bg: BackgroundTasks):
    """Analisa métricas com IA em background."""
    bg.add_task(_task_analisar)
    return {"status": "iniciado"}


async def _task_analisar():
    try:
        _push_log("🤖 IA analisando performance...", "ia")
        from analytics import analisar_com_ia

        loop = asyncio.get_event_loop()
        rec = await loop.run_in_executor(None, analisar_com_ia)
        if rec:
            _push_log("✅ Análise concluída — recomendações salvas", "ok")
        else:
            _push_log("⚠ Sem dados suficientes para análise", "warn")
    except Exception as e:
        _push_log(f"✗ Erro na análise: {e}", "err")
        logger.error("Erro na análise: %s", e, exc_info=True)


@app.get("/api/analytics/dados")
async def get_analytics_dados():
    """Retorna dados de métricas para os gráficos da interface."""
    try:
        from analytics import _carregar_dados_para_analise, obter_ultima_recomendacao

        banco.inicializar()
        dados = _carregar_dados_para_analise()
        rec = obter_ultima_recomendacao()
        return {
            "por_formato": dados.get("por_formato", []),
            "top_videos": dados.get("top_videos", []),
            "por_horario": dados.get("por_horario", []),
            "recomendacao": rec,
        }
    except Exception as e:
        logger.error("Erro ao buscar analytics: %s", e)
        return {
            "por_formato": [],
            "top_videos": [],
            "por_horario": [],
            "recomendacao": None,
        }


# ── Configurações ────────────────────────────────────


class ConfigRequest(BaseModel):
    nome_canal: Optional[str] = None
    idioma: Optional[str] = None
    modelo_whisper: Optional[str] = None
    postar_tiktok: Optional[bool] = None
    postar_youtube: Optional[bool] = None
    analytics_auto: Optional[bool] = None


@app.get("/api/config")
async def get_config():
    """Retorna configuração atual."""
    try:
        from config import cfg

        return {
            "nome_canal": cfg.nome_canal,
            "idioma": cfg.idioma,
            "modelo_whisper": cfg.modelo_whisper,
            "tem_anthropic": bool(cfg.chave_anthropic),
            "tem_elevenlabs": bool(cfg.chave_elevenlabs),
            "tem_telegram": cfg.tem_telegram(),
        }
    except Exception as e:
        return {"erro": str(e)}


@app.post("/api/config")
async def salvar_config(req: ConfigRequest):
    """
    Atualiza o config.py com novos valores.
    Para credenciais, o usuário deve editar o .env diretamente.
    """
    try:
        config_path = BASE_DIR / "config.py"
        src = config_path.read_text(encoding="utf-8")

        if req.nome_canal:
            src = _substituir_valor(src, "nome_canal", f'"{req.nome_canal}"')
        if req.idioma:
            src = _substituir_valor(src, "idioma", f'"{req.idioma}"')
        if req.modelo_whisper:
            src = _substituir_valor(src, "modelo_whisper", f'"{req.modelo_whisper}"')

        config_path.write_text(src, encoding="utf-8")

        # Recarregar config
        import config

        importlib.reload(config)

        _push_log("✅ Configurações salvas", "ok")
        return {"status": "salvo"}

    except Exception as e:
        logger.error("Erro ao salvar config: %s", e)
        raise HTTPException(500, str(e))


def _substituir_valor(src: str, campo: str, novo_valor: str) -> str:
    """Substitui valor de um campo no config.py preservando indentação."""
    return re.sub(rf"(\s+{campo}\s*=\s*)([^\n]+)", rf"\g<1>{novo_valor}", src)


@app.post("/api/config/testar")
async def testar_conexoes():
    """Testa todas as conexões configuradas."""
    resultado = {}

    # Anthropic
    try:
        from config import cfg

        if cfg.chave_anthropic:
            import anthropic

            cliente = anthropic.Anthropic(api_key=cfg.chave_anthropic)
            cliente.messages.create(
                model="claude-haiku-4",
                max_tokens=5,
                messages=[{"role": "user", "content": "ok"}],
            )
            resultado["anthropic"] = "ok"
        else:
            resultado["anthropic"] = "nao_configurado"
    except Exception as e:
        resultado["anthropic"] = f"erro: {str(e)[:60]}"

    # YouTube
    try:
        token = BASE_DIR / "token.json"
        resultado["youtube"] = "ok" if token.exists() else "nao_autenticado"
    except Exception:
        resultado["youtube"] = "erro"

    # TikTok
    try:
        token = BASE_DIR / "token_tiktok.json"
        resultado["tiktok"] = "ok" if token.exists() else "nao_autenticado"
    except Exception:
        resultado["tiktok"] = "erro"

    # Telegram
    try:
        from config import cfg

        resultado["telegram"] = "ok" if cfg.tem_telegram() else "nao_configurado"
    except Exception:
        resultado["telegram"] = "erro"

    return resultado


# ── URLs diárias ─────────────────────────────────────


@app.get("/api/urls-diarias")
async def get_urls_diarias():
    path = BASE_DIR / "urls_diarias.txt"
    if path.exists():
        return {"conteudo": path.read_text(encoding="utf-8")}
    return {"conteudo": ""}


@app.post("/api/urls-diarias")
async def salvar_urls_diarias(body: dict):
    path = BASE_DIR / "urls_diarias.txt"
    path.write_text(body.get("conteudo", ""), encoding="utf-8")
    return {"status": "salvo"}


# ── Output — listar vídeos gerados ───────────────────


@app.get("/api/output/listar")
async def listar_output():
    """Lista arquivos na pasta output/."""
    output_dir = BASE_DIR / "output"
    if not output_dir.exists():
        return {"arquivos": []}
    arquivos = []
    for f in sorted(
        output_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True
    )[:20]:
        txt = f.with_suffix(".txt")
        arquivos.append(
            {
                "nome": f.name,
                "tamanho_mb": round(f.stat().st_size / 1024 / 1024, 1),
                "criado_em": datetime.fromtimestamp(f.stat().st_mtime).strftime(
                    "%d/%m %H:%M"
                ),
                "tem_txt": txt.exists(),
            }
        )
    return {"arquivos": arquivos}


@app.get("/api/output/download/{nome}")
async def download_output(nome: str):
    """Faz download de um arquivo da pasta output/."""
    try:
        path = secure_path("output", nome)
    except ValueError:
        raise HTTPException(404, "Arquivo não encontrado")
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(str(path), filename=path.name)


# ── Health ───────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "processando": _estado["processando"],
        "daemon": _estado["daemon_ativo"],
        "hora": datetime.now().strftime("%H:%M:%S"),
    }


# ── Main ─────────────────────────────────────────────

if __name__ == "__main__":
    import threading
    import webbrowser

    # Validar configuração antes de iniciar o servidor
    from config import cfg

    erros = cfg.validar_chaves()
    if erros:
        print("\n❌ Configuração incompleta:")
        for e in erros:
            print(f"\n{e}")
        print("\nCorrija o .env e tente novamente.")
        sys.exit(1)

    print("\n" + "═" * 55)
    print("  BoomVibes — Dashboard Local")
    print("═" * 55)
    print("\n  ✅ Iniciando em: http://localhost:8000")
    print("  Ctrl+C para parar\n")

    # Abrir navegador após 1.5s
    def abrir_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=abrir_browser, daemon=True).start()

    uvicorn.run(
        app,
        host="127.0.0.1",  # uso local apenas — painel controla postagem e
        # gasto de API, não expor a outros dispositivos
        # da rede sem necessidade real (ver QA scan)
        port=8000,
        log_level="warning",  # silenciar logs do uvicorn no terminal
    )
