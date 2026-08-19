#!/usr/bin/env python3
"""
=======================================================
  YOUTUBE → SHORTS — Pipeline Completo com IA + Banco
=======================================================
  1. Verifica banco — pula vídeos já processados
  2. Baixa vídeo do YouTube (yt-dlp)
  3. Transcreve o áudio (Whisper)
  4. IA seleciona cortes com gancho nos 3 primeiros segundos
  5. Corta e processa para Shorts (9:16, legendas, logo, pitch)
  6. Registra tudo no banco (banco_shorts.db)

  Uso:
    python youtube_para_shorts.py
    python youtube_para_shorts.py --url https://youtu.be/xxx
    python youtube_para_shorts.py --url URL --chave SUA_CHAVE
    python youtube_para_shorts.py --url URL --forcar   (reprocessa mesmo se já existir)
=======================================================
"""

import os, sys, json, re, shutil, argparse, subprocess, tempfile
from pathlib import Path
from datetime import datetime
from typing import Any
from logger_setup import get_logger
from retry import chamar_anthropic
from telegram import notificar
import banco
from config import cfg
from constantes import CORES_ASS, EXTENSOES_VIDEO_VALIDAS
try:
    import whisper
except ImportError:
    whisper = None
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
import anthropic

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════
#  CONFIGURAÇÕES — edite em config.py
# ═══════════════════════════════════════════════════════

# Atalhos para compatibilidade
CHAVE_ANTHROPIC     = cfg.chave_anthropic
MODELO_CLAUDE       = cfg.modelo_claude
PASTA_DOWNLOADS     = str(cfg.pasta_downloads)
PASTA_CORTES        = str(cfg.pasta_cortes)
PASTA_PRONTOS       = str(cfg.pasta_prontos)
NOME_CANAL          = cfg.nome_canal
COR_LEGENDA         = cfg.cor_legenda
TAMANHO_FONT        = cfg.tamanho_font
QUALIDADE_CRF       = cfg.qualidade_crf
VELOCIDADE_ENC      = cfg.velocidade_enc
PITCH_VALOR         = cfg.pitch_valor
MODELO_WHISPER      = cfg.modelo_whisper
IDIOMA              = cfg.idioma
DURACAO_GLOBAL_MIN  = cfg.duracao_global_min
DURACAO_GLOBAL_MAX  = cfg.duracao_global_max
GERAR_DESCRICAO     = True
# ═══════════════════════════════════════════════════════

# CORES_ASS agora vem de constantes.py

def log(msg: str, nivel: str = "INFO") -> None:
    hora = datetime.now().strftime("%H:%M:%S")
    p = {"INFO": "✓", "ERRO": "✗", "AVISO": "⚠", "PROC": "→", "IA": "🤖", "DB": "🗄️"}
    print(f"[{hora}] {p.get(nivel,'·')} {msg}")

# ─── VERIFICAÇÃO ─────────────────────────────────────────

def verificar_deps() -> None:
    erros = []
    if not shutil.which("ffmpeg"):
        erros.append("FFmpeg não instalado → https://ffmpeg.org/download.html")
    for pkg, nome in [("yt_dlp","yt-dlp"),("whisper","openai-whisper"),("anthropic","anthropic")]:
        try:
            __import__(pkg)
        except ImportError:
            erros.append(f"{nome} não instalado → pip install {nome}")
    if erros:
        print("\n❌ Dependências faltando:\n")
        for e in erros: print(f"   • {e}")
        sys.exit(1)
    if not CHAVE_ANTHROPIC:
        print("\n❌ Chave da API Anthropic não configurada.")
        print("   Crie em: https://console.anthropic.com")
        print("   Depois: export ANTHROPIC_API_KEY=sua_chave")
        sys.exit(1)
    log("Todas as dependências OK")

# ─── ETAPA 1: DOWNLOAD ───────────────────────────────────

def baixar_video(url: str, pasta_destino: Path) -> tuple:
    if not yt_dlp:
        raise RuntimeError("yt-dlp não instalado → pip install yt-dlp")
    pasta_destino = Path(pasta_destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    log(f"Baixando: {url}", "PROC")

    opcoes = {
        "outtmpl":             str(pasta_destino / "%(id)s_%(title).60s.%(ext)s"),
        "format":              "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet":               True,
        "no_warnings":         True,
    }

    with yt_dlp.YoutubeDL(opcoes) as ydl:
        info    = ydl.extract_info(url, download=True)
        titulo  = info.get("title", "video")
        duracao = info.get("duration", 0)

    candidatos = sorted(pasta_destino.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not candidatos:
        raise FileNotFoundError("Arquivo MP4 não encontrado após download.")

    caminho = candidatos[0]
    log(f"Baixado: {caminho.name} ({int(duracao//60)}min {int(duracao%60)}s)")
    return caminho, titulo, duracao

# ─── ETAPA 2: TRANSCRIÇÃO ────────────────────────────────

def transcrever(caminho_video: Path) -> list:
    if not whisper:
        raise RuntimeError("whisper não instalado → pip install openai-whisper")
    log(f"Transcrevendo com Whisper ({MODELO_WHISPER})....", "PROC")
    modelo = whisper.load_model(MODELO_WHISPER)
    idioma = None if IDIOMA == "auto" else IDIOMA
    resultado = modelo.transcribe(str(caminho_video), language=idioma, verbose=False)
    segmentos = resultado["segments"]
    log(f"Transcrição: {len(segmentos)} segmentos")
    return segmentos

def segmentos_para_texto(segmentos: list) -> str:
    linhas = []
    for s in segmentos:
        ini = f"{int(s['start']//60):02d}:{int(s['start']%60):02d}"
        fim = f"{int(s['end']//60):02d}:{int(s['end']%60):02d}"
        linhas.append(f"[{ini}-{fim}] {s['text'].strip()}")
    return "\n".join(linhas)

# ─── ETAPA 3: IA SELECIONA CORTES ────────────────────────

def ia_selecionar_cortes(transcricao_texto: str, duracao_total: float, titulo: str) -> tuple:
    log("IA selecionando cortes para Shorts...", "IA")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Você é especialista em criar Shorts virais no YouTube com foco em conteúdo religioso e espiritual.

Analise a transcrição do vídeo "{titulo}" (duração: {duracao_total:.0f}s) e selecione o MÁXIMO de cortes possível.

REGRAS OBRIGATÓRIAS:
1. DURAÇÃO: "denso" = 50 a 59s | "impacto" = 30 a 45s
2. GANCHO: os primeiros 3s DEVEM começar com frase de impacto, pergunta ou afirmação forte
3. COMPLETUDE: começo, meio e fim — nunca cortar no meio de frase
4. SEM SOBREPOSIÇÃO: timestamps não se repetem
5. MÁXIMO: maior número possível de cortes

TRANSCRIÇÃO:
{transcricao_texto}

Responda SOMENTE com JSON puro, sem markdown:
[{{"tipo":"denso","inicio":45.0,"fim":103.0,"titulo":"Título impactante","gancho":"Frase exata dos 3s iniciais","motivo":"Por que vai bombar"}}]"""

    resposta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    # Estimar custo aproximado (claude-sonnet ~$3/M input, $15/M output)
    tokens_in  = resposta.usage.input_tokens
    tokens_out = resposta.usage.output_tokens
    custo_usd  = (tokens_in * 3 + tokens_out * 15) / 1_000_000

    texto = resposta.content[0].text.strip()
    texto = re.sub(r"```json|```", "", texto).strip()

    try:
        cortes = json.loads(texto)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', texto, re.DOTALL)
        if match:
            cortes = json.loads(match.group())
        else:
            raise ValueError(f"IA retornou formato inválido:\n{texto}")

    log(f"IA selecionou {len(cortes)} cortes (custo: ${custo_usd:.4f})", "IA")
    return cortes, custo_usd

def ia_gerar_descricao(corte: dict, titulo_video: str):
    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Crie conteúdo de publicação para um YouTube Short religioso.

Vídeo: "{titulo_video}"
Título do corte: "{corte.get('titulo','')}"
Gancho: "{corte.get('gancho','')}"
Tipo: {corte.get('tipo','denso')}

Responda SOMENTE com JSON puro:
{{"titulo_yt":"Título com emoji (máx 80 chars)","descricao":"3-4 linhas com CTA para seguir","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE, max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    tokens_in  = resposta.usage.input_tokens
    tokens_out = resposta.usage.output_tokens
    custo_usd  = (tokens_in * 3 + tokens_out * 15) / 1_000_000

    texto = re.sub(r"```json|```", "", resposta.content[0].text.strip()).strip()
    try:
        return json.loads(texto), custo_usd
    except Exception:
        return None, custo_usd

# ─── ETAPA 4: CORTAR VÍDEO ───────────────────────────────

def cortar_video(caminho_video: Path, cortes: list, pasta_saida: Path) -> list:
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    arquivos = []

    for i, corte in enumerate(cortes, 1):
        inicio = float(corte["inicio"])
        fim    = min(float(corte["fim"]), inicio + DURACAO_GLOBAL_MAX)
        tipo   = corte.get("tipo", "denso")

        nome_safe = re.sub(r'[^\w\s-]', '', corte.get("titulo", f"corte_{i}"))[:35].strip()
        nome_safe = re.sub(r'\s+', '_', nome_safe)
        nome_arq  = f"{i:02d}_{tipo}_{nome_safe}.mp4"
        dest      = pasta_saida / nome_arq

        log(f"Cortando [{i}/{len(cortes)}]: {inicio:.1f}s → {fim:.1f}s ({fim-inicio:.0f}s | {tipo})", "PROC")

        cmd = ["ffmpeg","-y","-ss",str(inicio),"-to",str(fim),"-i",str(caminho_video),
               "-c","copy","-avoid_negative_ts","make_zero",str(dest)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=cfg.timeout_ffmpeg_corte)
        if res.returncode == 0:
            log(f"  ✓ {nome_arq}")
            arquivos.append({"caminho": dest, "corte": corte})
        else:
            log(f"  ✗ Erro: {res.stderr[-100:]}", "ERRO")

    return arquivos

# ─── ETAPA 5: PROCESSAR PARA SHORTS ──────────────────────

def gerar_ass(segmentos: list, inicio_corte: float, fim_corte: float, caminho_saida: Path) -> None:
    cor    = CORES_ASS.get(COR_LEGENDA, "&H00FFFFFF")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{TAMANHO_FONT},{cor},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def t2ass(s: float) -> str:
        h = int(s//3600); m = int((s%3600)//60); sc = s%60
        return f"{h}:{m:02d}:{sc:05.2f}"

    linhas = [header]
    for seg in segmentos:
        if seg["end"] <= inicio_corte or seg["start"] >= fim_corte:
            continue
        t_ini = max(0.0, seg["start"] - inicio_corte)
        t_fim = min(fim_corte - inicio_corte, seg["end"] - inicio_corte)
        texto = seg["text"].strip().replace("\n", " ")
        if len(texto) > 38:
            meio = len(texto)//2
            esp  = texto.rfind(" ", 0, meio)
            if esp > 0:
                texto = texto[:esp] + r"\N" + texto[esp+1:]
        linhas.append(f"Dialogue: 0,{t2ass(t_ini)},{t2ass(t_fim)},Default,,0,0,0,,{texto}")

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

def processar_para_shorts(arquivo_corte: dict, segmentos: list, pasta_saida: Path, titulo_video: str):
    caminho_entrada = arquivo_corte["caminho"]
    corte           = arquivo_corte["corte"]
    inicio_corte    = float(corte["inicio"])
    fim_corte       = float(corte["fim"])

    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    ts          = datetime.now().strftime("%H%M%S")
    nome_saida  = f"short_{caminho_entrada.stem}_{ts}.mp4"
    txt_saida   = pasta_saida / f"short_{caminho_entrada.stem}_{ts}.txt"
    caminho_out = pasta_saida / nome_saida

    log(f"Processando: {caminho_entrada.name}", "PROC")

    with tempfile.TemporaryDirectory() as tmp:
        tmp      = Path(tmp)
        ass_path = tmp / "legendas.ass"
        gerar_ass(segmentos, inicio_corte, fim_corte, ass_path)

        ass_esc  = str(ass_path).replace("\\","/").replace(":","\\:")
        nome_esc = NOME_CANAL.replace("@","\\@")

        vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            f"ass='{ass_esc}',"
            f"drawtext=text='{nome_esc}':fontcolor=white:fontsize=26:"
            "box=1:boxcolor=black@0.55:boxborderw=8:x=w-tw-20:y=24"
        )
        af = f"atempo={PITCH_VALOR},asetrate=44100*{PITCH_VALOR},aresample=44100"

        cmd = [
            "ffmpeg","-y","-i",str(caminho_entrada),
            "-vf",vf,"-af",af,
            "-c:v","libx264","-crf",str(QUALIDADE_CRF),"-preset",VELOCIDADE_ENC,
            "-profile:v","high","-level","4.1","-pix_fmt","yuv420p","-r","30",
            "-movflags","+faststart",
            "-c:a","aac","-b:a","192k","-ar","44100",
            "-map_metadata","-1",
            "-metadata","title=","-metadata","comment=","-metadata","encoder=",
            str(caminho_out)
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=cfg.timeout_ffmpeg_encode)
        if res.returncode != 0:
            log(f"Erro FFmpeg: {res.stderr[-200:]}", "ERRO")
            return None, None, 0.0

        tam = caminho_out.stat().st_size / (1024*1024)
        log(f"✅ Short pronto: {nome_saida} ({tam:.1f} MB)")

    # Gerar descrição
    desc_info = None
    custo_desc = 0.0
    if GERAR_DESCRICAO:
        log("IA gerando título + descrição + hashtags...", "IA")
        desc_info, custo_desc = ia_gerar_descricao(corte, titulo_video)
        if desc_info:
            hashtags_str = " ".join(desc_info.get("hashtags", []))
            conteudo = (
                f"TÍTULO:\n{desc_info.get('titulo_yt', corte.get('titulo',''))}\n\n"
                f"DESCRIÇÃO:\n{desc_info.get('descricao','')}\n\n"
                f"HASHTAGS:\n{hashtags_str}\n\n"
                f"GANCHO (primeiros 3s):\n{corte.get('gancho','')}\n"
            )
            txt_saida.write_text(conteudo, encoding="utf-8")
            log(f"📝 {txt_saida.name}")

    return caminho_out, (txt_saida if desc_info else None), custo_desc, desc_info

# ─── PIPELINE PRINCIPAL ───────────────────────────────────

def pipeline(url: str, forcar: bool = False) -> list:
    # Importar banco
    banco.inicializar()
    usar_banco = True

    print("\n" + "═"*58)
    print("  YOUTUBE → SHORTS — Pipeline com IA + Banco")
    print("═"*58 + "\n")

    verificar_deps()

    for p in [PASTA_DOWNLOADS, PASTA_CORTES, PASTA_PRONTOS]:
        Path(p).mkdir(exist_ok=True)

    # ── Verificar banco ──────────────────────────────────
    if usar_banco and not forcar:
        registro = banco.video_ja_processado(url)
        if registro:
            print(f"\n⚠️  Este vídeo já foi processado anteriormente!")
            print(f"   Título : {registro['titulo']}")
            print(f"   Cortes : {registro['num_cortes']}")
            print(f"   Data   : {registro['criado_em']}")
            print(f"\n   Use --forcar para reprocessar mesmo assim.")
            print(f"   Os Shorts já gerados estão em: {Path(PASTA_PRONTOS).resolve()}\n")
            # Mostrar cortes existentes
            cortes_existentes = banco.listar_cortes(video_id=registro["id"])
            if cortes_existentes:
                print(f"   Cortes existentes:")
                for c in cortes_existentes:
                    status = c['status'].upper()
                    print(f"     [{c['numero']:02d}] {c['tipo']:6} | {c['duracao_s']:.0f}s | {status} | {c['titulo']}")
            print()
            return []

    # ── 1. Download ──────────────────────────────────────
    print("\n📥 ETAPA 1: Download\n" + "─"*45)
    caminho_video, titulo, duracao = baixar_video(url, PASTA_DOWNLOADS)

    video_id = None
    if usar_banco:
        video_id = banco.registrar_video(url, titulo, duracao, caminho_video)
        log(f"Vídeo registrado no banco (ID: {video_id})", "DB")

    # ── 2. Transcrição ───────────────────────────────────
    print("\n🎙  ETAPA 2: Transcrição\n" + "─"*45)
    segmentos = transcrever(caminho_video)
    transcricao_texto = segmentos_para_texto(segmentos)

    if usar_banco and video_id:
        banco.marcar_transcrito(video_id)

    # ── 3. IA seleciona cortes ───────────────────────────
    print("\n🤖 ETAPA 3: IA selecionando cortes\n" + "─"*45)
    cortes, custo_cortes = ia_selecionar_cortes(transcricao_texto, duracao, titulo)

    if usar_banco and video_id:
        banco.atualizar_custo(video_id, custo_cortes)

    # Filtrar durações
    cortes_validos = []
    for c in cortes:
        dur = float(c["fim"]) - float(c["inicio"])
        if DURACAO_GLOBAL_MIN <= dur <= DURACAO_GLOBAL_MAX:
            cortes_validos.append(c)
        else:
            log(f"Descartado ({dur:.0f}s): {c.get('titulo','')}", "AVISO")

    if not cortes_validos:
        log("Nenhum corte válido. Tente --modelo small.", "ERRO")
        sys.exit(1)

    print(f"\n   {len(cortes_validos)} cortes selecionados:\n")
    for i, c in enumerate(cortes_validos, 1):
        dur = float(c["fim"]) - float(c["inicio"])
        print(f"   [{i:02d}] {c['tipo'].upper():6} | {dur:.0f}s | {c['titulo']}")
        print(f"         Gancho : \"{c.get('gancho','—')}\"")
        print(f"         Motivo : {c.get('motivo','—')}\n")

    # ── 4. Cortar ────────────────────────────────────────
    print(f"\n✂️  ETAPA 4: Cortando {len(cortes_validos)} trechos\n" + "─"*45)
    arquivos_cortados = cortar_video(caminho_video, cortes_validos, PASTA_CORTES)

    # ── 5. Processar ─────────────────────────────────────
    print(f"\n🎬 ETAPA 5: Processando para Shorts\n" + "─"*45)
    prontos    = []
    custo_desc_total = 0.0

    for i, arq in enumerate(arquivos_cortados, 1):
        video_out, txt_out, custo_desc, desc_info_atual = processar_para_shorts(
            arq, segmentos, PASTA_PRONTOS, titulo
        )
        custo_desc_total += custo_desc

        if video_out:
            prontos.append((video_out, txt_out))

            # Registrar corte no banco
            if usar_banco and video_id:
                corte_info = arq["corte"]
                corte_info["categoria"] = "podcast"
                corte_id = banco.registrar_corte(
                    video_id    = video_id,
                    numero      = i,
                    corte_info  = corte_info,
                    caminho_video = video_out,
                    caminho_txt   = txt_out,
                    desc_info     = desc_info_atual
                )
                log(f"Corte registrado no banco (ID: {corte_id})", "DB")

    if usar_banco and video_id:
        banco.atualizar_custo(video_id, custo_desc_total)
        custo_total = custo_cortes + custo_desc_total
        log(f"Custo total API: ${custo_total:.4f} (~R${custo_total*5.6:.2f})", "DB")

    # ── Resumo ───────────────────────────────────────────
    print("\n" + "═"*58)
    print(f"  ✅ CONCLUÍDO: {len(prontos)}/{len(cortes_validos)} Shorts prontos")
    print(f"  📁 Saída: {Path(PASTA_PRONTOS).resolve()}")
    if usar_banco:
        s = banco.stats()
        print(f"  🗄️  Banco: {s['total_videos']} vídeos | {s['total_cortes']} cortes totais | {s['postados']} postados")
    print("═"*58 + "\n")
    notificar.pipeline_concluido(
        origem="YouTube → Shorts",
        total=len(cortes_validos),
        sucesso=len(prontos),
        custo_usd=custo_cortes + custo_desc_total
    )

    if prontos:
        print("Shorts prontos para publicar:\n")
        for video, txt in prontos:
            print(f"   🎥 {video.name}")
            if txt:
                print(f"   📝 {txt.name}")
            print()

    return prontos

# ─── ENTRADA ──────────────────────────────────────────────

def main():
    # FIX: usar cfg em vez de globals mutáveis
    parser = argparse.ArgumentParser(
        description="YouTube → Shorts com IA + Banco de histórico"
    )
    parser.add_argument("--url",    help="URL do vídeo do YouTube")
    parser.add_argument("--chave",  help="Chave API Anthropic")
    parser.add_argument("--modelo", default=MODELO_WHISPER,
                        choices=["tiny","base","small","medium","large"])
    parser.add_argument("--forcar", action="store_true",
                        help="Reprocessa mesmo se o vídeo já estiver no banco")
    args = parser.parse_args()

    if args.chave:   cfg.chave_anthropic = args.chave
    if args.modelo:  cfg.modelo_whisper  = args.modelo

    url = args.url
    if not url:
        print("\n" + "═"*58)
        print("  YOUTUBE → SHORTS — Pipeline com IA + Banco")
        print("═"*58)
        url = input("\n📎 Cole a URL do vídeo do YouTube: ").strip()
        if not url:
            print("URL não informada. Saindo.")
            sys.exit(1)

    pipeline(url, forcar=args.forcar)

if __name__ == "__main__":
    main()