#!/usr/bin/env python3
"""
=======================================================
  PIPELINE DIÁRIO COMPLETO
=======================================================
  Encadeia tudo em sequência automaticamente:

  1. Gerador de conteúdo (reflexão + história + versículo)
  2. Cortes de podcast de URLs agendadas (opcional)
  3. Agendamento automático de todos os prontos
  4. Resumo diário via Telegram

  Rode manualmente:
    python run_diario.py

  Ou configure o cron para rodar todo dia às 6h:
    python run_diario.py --instalar-cron

  Verificar cron instalado:
    python run_diario.py --status

  Remover cron:
    python run_diario.py --remover-cron
=======================================================
"""

import argparse
import json
import platform
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

# ── Setup inicial ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import banco
from config import cfg
from logger_setup import get_logger
from telegram import notificar

try:
    from analytics import analisar_com_ia, coletar_metricas, obter_config_otimizada

    ANALYTICS_DISPONIVEL = True
except ImportError:
    ANALYTICS_DISPONIVEL = False

try:
    from fundos import garantir_minimo as _garantir_fundos

    FUNDOS_DISPONIVEL = True
except ImportError:
    FUNDOS_DISPONIVEL = False

logger = get_logger(__name__)

# ── CONFIGURAÇÕES DO PIPELINE DIÁRIO ─────────────────────
# Arquivo com URLs de podcasts para processar diariamente
# Formato: uma URL por linha
ARQUIVO_URLS = Path("urls_diarias.txt")

# Formatos a gerar por dia
FORMATOS_DIARIOS = ["reflexao", "historia", "versiculo"]

# Horário do cron (padrão: 6h da manhã)
CRON_HORA = 6
CRON_MINUTO = 0
# ─────────────────────────────────────────────────────────


def log(msg: str, nivel: str = "INFO") -> None:
    hora = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "✓", "ERRO": "✗", "AVISO": "⚠", "PROC": "→"}
    print(f"[{hora}] {icons.get(nivel, '·')} {msg}")
    if nivel == "ERRO":
        logger.error(msg)
    elif nivel == "AVISO":
        logger.warning(msg)
    else:
        logger.info(msg)


def cabecalho():
    print("\n" + "═" * 58)
    print(f"  PIPELINE DIÁRIO — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("═" * 58 + "\n")


# ── ETAPA 1: Gerar conteúdo original ─────────────────────


def etapa_gerar_conteudo() -> dict:
    """Roda o gerador de conteúdo e retorna resultado."""
    print("\n🎬 ETAPA 1: Gerando conteúdo original\n" + "─" * 45)

    resultado = {"gerados": 0, "erros": 0, "custo_usd": 0.0}

    try:
        # Importar e rodar gerador
        from gerador_conteudo import gerar_videos_do_dia

        prontos = gerar_videos_do_dia(formatos=FORMATOS_DIARIOS)
        resultado["gerados"] = len(prontos)
        log(f"Gerador: {len(prontos)} vídeos criados")

    except Exception as e:
        resultado["erros"] += 1
        log(f"Erro no gerador: {e}", "ERRO")
        notificar.erro("run_diario → gerador", str(e), excecao=e)
        logger.error("Traceback gerador:\n%s", traceback.format_exc())

    return resultado


# ── ETAPA 2: Processar URLs de podcasts ──────────────────


def etapa_processar_urls() -> dict:
    """Lê urls_diarias.txt e processa cada URL."""
    print("\n📥 ETAPA 2: Processando podcasts do YouTube\n" + "─" * 45)

    resultado = {"processados": 0, "erros": 0, "cortes": 0}

    if not ARQUIVO_URLS.exists():
        log(f"'{ARQUIVO_URLS}' não encontrado — pulando etapa de podcasts", "AVISO")
        log("Crie o arquivo com uma URL por linha para ativar esta etapa")
        return resultado

    urls = [
        linha.strip()
        for linha in ARQUIVO_URLS.read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    ]

    if not urls:
        log("Nenhuma URL em urls_diarias.txt — pulando", "AVISO")
        return resultado

    log(f"{len(urls)} URL(s) para processar")

    try:
        from youtube_para_shorts import pipeline

        for url in urls:
            try:
                log(f"Processando: {url}", "PROC")
                prontos = pipeline(url)
                resultado["processados"] += 1
                resultado["cortes"] += len(prontos)
                log(f"  → {len(prontos)} cortes gerados")
            except Exception as e:
                resultado["erros"] += 1
                log(f"  → Erro: {e}", "ERRO")
                notificar.erro(
                    "run_diario → youtube", f"Falha em {url}: {e}", excecao=e
                )
                logger.error("Traceback URL %s:\n%s", url, traceback.format_exc())

    except ImportError as e:
        log(f"Erro ao importar youtube_para_shorts: {e}", "ERRO")

    return resultado


# ── ETAPA 3: Agendar todos os prontos ────────────────────


def etapa_agendar() -> dict:
    """Agenda automaticamente todos os cortes com status 'pronto'."""
    print("\n📅 ETAPA 3: Agendando vídeos prontos\n" + "─" * 45)

    resultado = {"agendados": 0, "erros": 0}

    try:
        from agendador import agendar_lote

        banco.inicializar()

        prontos_antes = len(banco.listar_cortes(status="pronto"))

        if prontos_antes == 0:
            log("Nenhum corte pronto para agendar")
            return resultado

        agendar_lote()

        prontos_depois = len(banco.listar_cortes(status="pronto"))
        resultado["agendados"] = prontos_antes - prontos_depois
        log(f"Agendados: {resultado['agendados']} cortes")

    except Exception as e:
        resultado["erros"] += 1
        log(f"Erro no agendador: {e}", "ERRO")
        notificar.erro("run_diario → agendador", str(e), excecao=e)
        logger.error("Traceback agendador:\n%s", traceback.format_exc())

    return resultado


# ── ETAPA 4: Resumo e notificação ────────────────────────


def etapa_resumo(r1: dict, r2: dict, r3: dict, inicio: datetime) -> None:
    """Imprime resumo e envia via Telegram."""
    print("\n📊 RESUMO DO DIA\n" + "─" * 45)

    duracao = (datetime.now() - inicio).total_seconds()
    mins = int(duracao // 60)
    segs = int(duracao % 60)

    try:
        s = banco.stats()
    except Exception:
        s = {}

    total_gerados = r1["gerados"] + r2["cortes"]
    total_erros = r1["erros"] + r2["erros"] + r3["erros"]
    custo = s.get("custo_total_usd", 0.0)
    agendados_hoje = r3["agendados"]
    postados_total = s.get("postados", 0)

    print(f"  Conteúdo gerado   : {r1['gerados']} originais + {r2['cortes']} cortes")
    print(f"  URLs processadas  : {r2['processados']}")
    print(f"  Agendados hoje    : {agendados_hoje}")
    print(f"  Total já postados : {postados_total}")
    print(f"  Erros encontrados : {total_erros}")
    print(f"  Tempo total       : {mins}min {segs}s")
    print(f"  Custo API acum.   : ${custo:.4f} (~R${custo*5.6:.2f})")

    status = (
        "✅ Concluído"
        if total_erros == 0
        else f"⚠️ Concluído com {total_erros} erro(s)"
    )
    print(f"\n  {status}")
    print("═" * 58 + "\n")

    # Enviar resumo via Telegram
    notificar.resumo_diario(
        gerados=total_gerados,
        postados=postados_total,
        agendados=agendados_hoje,
        custo_usd=custo,
    )

    # Alertar se custo acumulado > R$30 (~$5)
    if custo > 5.0:
        notificar.saldo_baixo(custo_total_usd=custo, limite_usd=5.0)

    # Salvar resultado do dia em JSON para histórico
    historico_path = Path("logs") / "historico_diario.jsonl"
    historico_path.parent.mkdir(exist_ok=True)
    registro = {
        "data": datetime.now().strftime("%Y-%m-%d"),
        "hora": datetime.now().strftime("%H:%M:%S"),
        "gerados": total_gerados,
        "agendados": agendados_hoje,
        "postados": postados_total,
        "erros": total_erros,
        "custo_usd": custo,
        "duracao_s": int(duracao),
    }
    with open(historico_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    log(f"Histórico salvo: {historico_path}")


# ── PIPELINE PRINCIPAL ────────────────────────────────────


def rodar_pipeline() -> None:
    """Executa o pipeline diário completo."""
    inicio = datetime.now()
    cabecalho()

    # Verificar configuração
    erros_cfg = cfg.validar_chaves()
    if erros_cfg:
        for e in erros_cfg:
            log(e, "ERRO")
        notificar.erro("run_diario", "Chave de API não configurada")
        sys.exit(1)

    cfg.criar_pastas()

    # Garantir assets mínimos antes de gerar
    if FUNDOS_DISPONIVEL:
        try:
            log("Verificando assets (fundos e músicas)...", "PROC")
            _garantir_fundos()
        except Exception as e:
            log(f"Aviso: não foi possível verificar assets: {e}", "AVISO")

    # Rodar etapas
    r1 = etapa_gerar_conteudo()
    r2 = etapa_processar_urls()
    r3 = etapa_agendar()
    etapa_resumo(r1, r2, r3, inicio)

    # Coletar métricas semanalmente (toda segunda-feira)
    if ANALYTICS_DISPONIVEL:
        from datetime import datetime as _dt

        if _dt.now().weekday() == 0:  # 0 = segunda-feira
            log("Segunda-feira: coletando métricas e analisando performance...", "PROC")
            try:
                coletar_metricas(dias_atras=7)
                analisar_com_ia()
                log(
                    "Análise de performance concluída — veja: python analytics.py --recomendacoes"
                )
            except Exception as e:
                log(f"Erro na análise: {e}", "AVISO")


# ── GERENCIAMENTO DO CRON ─────────────────────────────────


def _caminho_python() -> str:
    """Retorna o caminho absoluto do Python atual."""
    return sys.executable


def _linha_cron() -> str:
    """Retorna a linha cron para este script."""
    script = Path(__file__).resolve()
    python = _caminho_python()
    log_file = script.parent / "logs" / "cron.log"
    return (
        f"{CRON_MINUTO} {CRON_HORA} * * * "
        f"cd {script.parent} && "
        f"{python} {script} >> {log_file} 2>&1"
    )


def instalar_cron() -> None:
    """Instala o cron job para execução diária automática."""
    if platform.system() == "Windows":
        _instalar_task_scheduler()
        return

    linha = _linha_cron()

    try:
        # Ler crontab atual
        res = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        crontab_atual = res.stdout if res.returncode == 0 else ""

        # Verificar se já existe
        script_path = str(Path(__file__).resolve())
        if script_path in crontab_atual:
            log("Cron já instalado — nada a fazer")
            _mostrar_cron_atual()
            return

        # Adicionar nova linha
        novo_crontab = crontab_atual.rstrip() + "\n" + linha + "\n"
        proc = subprocess.run(
            ["crontab", "-"],
            input=novo_crontab,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if proc.returncode == 0:
            log("✅ Cron instalado com sucesso!")
            log(f"   Rodará todo dia às {CRON_HORA:02d}:{CRON_MINUTO:02d}h")
            log("   Logs em: logs/cron.log")
        else:
            log(f"Erro ao instalar cron: {proc.stderr}", "ERRO")

    except FileNotFoundError:
        log("'crontab' não encontrado. Use --instalar-cron no Mac/Linux.", "ERRO")


def _instalar_task_scheduler() -> None:
    """Instala tarefa agendada no Windows Task Scheduler."""
    script = Path(__file__).resolve()
    python = _caminho_python()
    nome = "PipelineDiarioShorts"

    cmd = [
        "schtasks",
        "/create",
        "/f",
        "/tn",
        nome,
        "/tr",
        f'"{python}" "{script}"',
        "/sc",
        "DAILY",
        "/st",
        f"{CRON_HORA:02d}:{CRON_MINUTO:02d}",
        "/rl",
        "HIGHEST",
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if res.returncode == 0:
        log(f"✅ Tarefa '{nome}' instalada no Windows Task Scheduler!")
        log(f"   Rodará todo dia às {CRON_HORA:02d}:{CRON_MINUTO:02d}h")
    else:
        log(f"Erro: {res.stderr}", "ERRO")
        log("Tente rodar como Administrador", "AVISO")


def remover_cron() -> None:
    """Remove o cron job deste script."""
    if platform.system() == "Windows":
        nome = "PipelineDiarioShorts"
        res = subprocess.run(
            ["schtasks", "/delete", "/f", "/tn", nome],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if res.returncode == 0:
            log(f"✅ Tarefa '{nome}' removida do Task Scheduler")
        else:
            log(f"Tarefa não encontrada ou erro: {res.stderr}", "AVISO")
        return

    script_path = str(Path(__file__).resolve())
    try:
        res = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if res.returncode != 0 or script_path not in res.stdout:
            log("Cron não estava instalado")
            return
        linhas_filtradas = [l for l in res.stdout.splitlines() if script_path not in l]
        novo = "\n".join(linhas_filtradas) + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=novo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        log("✅ Cron removido com sucesso")
    except FileNotFoundError:
        log("'crontab' não encontrado", "ERRO")


def _mostrar_cron_atual() -> None:
    try:
        res = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        script_path = str(Path(__file__).resolve())
        for linha in res.stdout.splitlines():
            if script_path in linha:
                print(f"\n  Linha instalada: {linha}\n")
    except Exception:
        # _mostrar_cron_atual() é só informativa: se 'crontab' não existir
        # ou falhar, a única consequência é não exibir a linha extra de
        # confirmação. Sem efeito colateral, sem caller dependente do
        # resultado, sem return nesta função.
        pass


def mostrar_status() -> None:
    """Mostra se o cron está instalado e o histórico recente."""

    print("\n" + "═" * 58)
    print("  STATUS DO PIPELINE DIÁRIO")
    print("═" * 58)

    # Status do cron
    if platform.system() == "Windows":
        nome = "PipelineDiarioShorts"
        res = subprocess.run(
            ["schtasks", "/query", "/tn", nome],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        instalado = res.returncode == 0
    else:
        try:
            res = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            script = str(Path(__file__).resolve())
            instalado = script in res.stdout
        except Exception:
            instalado = False

    status_cron = "✅ Instalado" if instalado else "❌ Não instalado"
    print(f"\n  Agendamento automático: {status_cron}")
    if instalado:
        print(f"  Horário: {CRON_HORA:02d}:{CRON_MINUTO:02d}h (todo dia)")

    # Histórico recente
    historico_path = Path("logs") / "historico_diario.jsonl"
    if historico_path.exists():
        linhas = historico_path.read_text(encoding="utf-8").strip().splitlines()
        ultimas = linhas[-5:]  # últimos 5 dias
        if ultimas:
            print("\n  Últimos dias:\n")
            print(
                f"  {'Data':>10}  {'Gerados':>7}  {'Postados':>8}  {'Erros':>5}  {'Custo':>8}"
            )
            print("  " + "─" * 50)
            for linha in reversed(ultimas):
                try:
                    d = json.loads(linha)
                    custo = f"R${d['custo_usd']*5.6:.2f}"
                    print(
                        f"  {d['data']:>10}  {d['gerados']:>7}  "
                        f"{d['postados']:>8}  {d['erros']:>5}  {custo:>8}"
                    )
                except Exception as e:
                    # Linha corrompida no JSONL: desaparece da tabela sem
                    # aviso se não logarmos aqui. Não interrompe a listagem
                    # dos demais dias, mas registra o problema.
                    logger.warning(
                        "Linha corrompida em historico_diario.jsonl, "
                        "pulando: %s — erro: %s",
                        linha[:80],
                        e,
                    )
    else:
        print("\n  Histórico: nenhuma execução registrada ainda")

    print()


# ── CLI ───────────────────────────────────────────────────


def main() -> None:
    global CRON_HORA, CRON_MINUTO
    parser = argparse.ArgumentParser(
        description="Pipeline diário automático — Shorts + TikTok"
    )
    parser.add_argument(
        "--instalar-cron",
        action="store_true",
        help=f"Instala execução automática todo dia às {CRON_HORA:02d}h",
    )
    parser.add_argument(
        "--remover-cron", action="store_true", help="Remove a execução automática"
    )
    parser.add_argument(
        "--status", action="store_true", help="Mostra status e histórico recente"
    )
    parser.add_argument(
        "--hora",
        type=int,
        default=CRON_HORA,
        help=f"Hora do cron (padrão: {CRON_HORA})",
    )
    parser.add_argument(
        "--minuto",
        type=int,
        default=CRON_MINUTO,
        help=f"Minuto do cron (padrão: {CRON_MINUTO})",
    )
    args = parser.parse_args()

    CRON_HORA = args.hora
    CRON_MINUTO = args.minuto

    if args.instalar_cron:
        instalar_cron()
    elif args.remover_cron:
        remover_cron()
    elif args.status:
        mostrar_status()
    else:
        rodar_pipeline()


if __name__ == "__main__":
    main()
