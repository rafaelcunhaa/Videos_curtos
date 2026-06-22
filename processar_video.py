#!/usr/bin/env python3
"""
=======================================================
  PROCESSADOR DE VÍDEO LOCAL → TIKTOK + YOUTUBE SHORTS
=======================================================
  Recebe um vídeo que você já tem no computador,
  a IA seleciona os melhores momentos e gera cortes
  prontos para postar no TikTok E YouTube Shorts.

  PIPELINE:
  1. Você indica o vídeo local
  2. Whisper transcreve o áudio completo
  3. IA seleciona os melhores cortes:
       • Denso  : 50–59s (ensinamento completo)
       • Impacto: 30–45s (momento emocional forte)
  4. FFmpeg corta nos pontos exatos
  5. Processa cada corte para TikTok + Shorts:
       • 9:16 vertical 1080x1920
       • Legendas automáticas queimadas
       • Nome do canal no canto
       • Recodificação (muda fingerprint)
       • Pitch ajustado (dificulta detecção)
       • Metadados apagados
       • 30fps, H.264 High 4.1
  6. Gera título + descrição + hashtags para cada corte
  7. Registra tudo no banco (banco_shorts.db)

  Uso:
    python processar_video.py
    python processar_video.py --arquivo meu_video.mp4
    python processar_video.py --arquivo meu_video.mp4 --chave sk-ant-...
    python processar_video.py --pasta ./videos   (processa todos da pasta)
    python processar_video.py --arquivo video.mp4 --forcar
=======================================================
"""

import os, sys, json, re, shutil, argparse, subprocess, tempfile
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════
#  CONFIGURAÇÕES — edite aqui antes de usar
# ═══════════════════════════════════════════════════════
CHAVE_ANTHROPIC = os.getenv("ANTHROPIC_API_KEY", "")  # ou cole: "sk-ant-..."
MODELO_CLAUDE   = "claude-sonnet-4-6"

PASTA_CORTES    = "cortes"
PASTA_PRONTOS   = "output"

NOME_CANAL      = "@SeuCanal"      # aparece no canto do vídeo
COR_LEGENDA     = "white"          # white | yellow | cyan
TAMANHO_FONT    = 20               # tamanho da legenda (18–24)
QUALIDADE_CRF   = 22               # 18=alta, 22=ótima, 28=comprimida
VELOCIDADE_ENC  = "medium"         # ultrafast | fast | medium | slow
PITCH_VALOR     = "1.02"           # +2% imperceptível — muda fingerprint

MODELO_WHISPER  = "base"           # tiny | base | small | medium | large
IDIOMA          = "pt"             # pt | en | auto

DURACAO_GLOBAL_MIN = 30            # mínimo de qualquer corte (segundos)
DURACAO_GLOBAL_MAX = 59            # máximo — limite monetização TikTok e Shorts

GERAR_DESCRICAO = True             # IA gera título + descrição + hashtags
# ═══════════════════════════════════════════════════════

CORES_ASS = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00"}
EXTENSOES_VALIDAS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}

def log(msg, nivel="INFO"):
    hora = datetime.now().strftime("%H:%M:%S")
    p = {"INFO":"✓","ERRO":"✗","AVISO":"⚠","PROC":"→","IA":"🤖","DB":"🗄️"}
    print(f"[{hora}] {p.get(nivel,'·')} {msg}")

# ─── VERIFICAÇÃO ─────────────────────────────────────────

def verificar_deps():
    erros = []
    if not shutil.which("ffmpeg"):
        erros.append("FFmpeg não instalado → https://ffmpeg.org/download.html")
    if not shutil.which("ffprobe"):
        erros.append("FFprobe não instalado (vem junto com FFmpeg)")
    for pkg, nome in [("whisper","openai-whisper"),("anthropic","anthropic")]:
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

# ─── INFO DO VÍDEO ───────────────────────────────────────

def obter_info_video(caminho):
    cmd = ["ffprobe","-v","quiet","-print_format","json",
           "-show_streams","-show_format", str(caminho)]
    res  = subprocess.run(cmd, capture_output=True, text=True)
    dados = json.loads(res.stdout)
    info  = {"duracao":0,"largura":0,"altura":0,"fps":30,"tem_audio":False}
    for s in dados.get("streams",[]):
        if s.get("codec_type") == "video":
            info["largura"] = int(s.get("width",0))
            info["altura"]  = int(s.get("height",0))
            fps_str = s.get("r_frame_rate","30/1")
            try:
                n, d = fps_str.split("/")
                info["fps"] = round(int(n)/int(d), 2)
            except Exception:
                info["fps"] = 30
        elif s.get("codec_type") == "audio":
            info["tem_audio"] = True
    info["duracao"] = float(dados.get("format",{}).get("duration",0))
    return info

# ─── ETAPA 1: TRANSCRIÇÃO ────────────────────────────────

def transcrever(caminho_video):
    import whisper
    log(f"Transcrevendo com Whisper ({MODELO_WHISPER})...", "PROC")
    modelo = whisper.load_model(MODELO_WHISPER)
    idioma = None if IDIOMA == "auto" else IDIOMA
    resultado = modelo.transcribe(str(caminho_video), language=idioma, verbose=False)
    segmentos  = resultado["segments"]
    log(f"Transcrição: {len(segmentos)} segmentos")
    return segmentos

def segmentos_para_texto(segmentos):
    linhas = []
    for s in segmentos:
        ini = f"{int(s['start']//60):02d}:{int(s['start']%60):02d}"
        fim = f"{int(s['end']//60):02d}:{int(s['end']%60):02d}"
        linhas.append(f"[{ini}-{fim}] {s['text'].strip()}")
    return "\n".join(linhas)

# ─── ETAPA 2: IA SELECIONA CORTES ────────────────────────

def ia_selecionar_cortes(transcricao_texto, duracao_total, titulo):
    import anthropic
    log("IA analisando e selecionando cortes...", "IA")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Você é especialista em criar conteúdo viral para TikTok e YouTube Shorts com foco em conteúdo religioso e espiritual.

Analise a transcrição do vídeo "{titulo}" (duração total: {duracao_total:.0f}s) e selecione o MÁXIMO de cortes possível para TikTok e Shorts.

REGRAS OBRIGATÓRIAS:
1. DURAÇÃO: "denso" = 50 a 59 segundos | "impacto" = 30 a 45 segundos
2. GANCHO: os primeiros 3 segundos DEVEM começar com frase de impacto, pergunta instigante ou afirmação forte — crítico para retenção
3. COMPLETUDE: cada corte tem começo, meio e fim — nunca cortar no meio de frase
4. SEM SOBREPOSIÇÃO: timestamps não se repetem entre cortes
5. MÁXIMO: selecione o maior número possível de cortes não sobrepostos

TIPOS:
- "denso"  : ensinamento completo, narrativa com profundidade, história — 50 a 59s
- "impacto": testemunho, revelação, frase poderosa, momento emocional — 30 a 45s

TRANSCRIÇÃO:
{transcricao_texto}

Responda SOMENTE com JSON puro, sem markdown, sem explicação:
[{{"tipo":"denso","inicio":45.0,"fim":103.0,"titulo":"Título impactante","gancho":"Frase exata dos 3s iniciais","motivo":"Por que vai viralizar"}}]"""

    resposta = cliente.messages.create(
        model=MODELO_CLAUDE, max_tokens=4096,
        messages=[{"role":"user","content":prompt}]
    )

    tokens_in  = resposta.usage.input_tokens
    tokens_out = resposta.usage.output_tokens
    custo_usd  = (tokens_in * 3 + tokens_out * 15) / 1_000_000

    texto = re.sub(r"```json|```","", resposta.content[0].text.strip()).strip()
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

def ia_gerar_descricao(corte, titulo_video):
    import anthropic
    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Crie conteúdo de publicação para um TikTok e YouTube Short religioso.

Vídeo: "{titulo_video}"
Título do corte: "{corte.get('titulo','')}"
Gancho (primeiros 3s): "{corte.get('gancho','')}"
Tipo: {corte.get('tipo','denso')}

Responda SOMENTE com JSON puro, sem markdown:
{{"titulo_yt":"Título com emoji (máx 80 chars)","titulo_tiktok":"Título TikTok chamativo (máx 60 chars)","descricao":"3-4 linhas com CTA para seguir o canal","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = cliente.messages.create(
        model=MODELO_CLAUDE, max_tokens=500,
        messages=[{"role":"user","content":prompt}]
    )
    tokens_in  = resposta.usage.input_tokens
    tokens_out = resposta.usage.output_tokens
    custo_usd  = (tokens_in * 3 + tokens_out * 15) / 1_000_000

    texto = re.sub(r"```json|```","", resposta.content[0].text.strip()).strip()
    try:
        return json.loads(texto), custo_usd
    except Exception:
        return None, custo_usd

# ─── ETAPA 3: CORTAR VÍDEO ───────────────────────────────

def cortar_video(caminho_video, cortes, pasta_saida):
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    arquivos = []

    for i, corte in enumerate(cortes, 1):
        inicio = float(corte["inicio"])
        fim    = min(float(corte["fim"]), inicio + DURACAO_GLOBAL_MAX)
        tipo   = corte.get("tipo","denso")

        nome_safe = re.sub(r'[^\w\s-]','', corte.get("titulo", f"corte_{i}"))[:35].strip()
        nome_safe = re.sub(r'\s+','_', nome_safe)
        nome_arq  = f"{i:02d}_{tipo}_{nome_safe}.mp4"
        dest      = pasta_saida / nome_arq

        log(f"Cortando [{i}/{len(cortes)}]: {inicio:.1f}s → {fim:.1f}s ({fim-inicio:.0f}s | {tipo})", "PROC")

        cmd = ["ffmpeg","-y","-ss",str(inicio),"-to",str(fim),
               "-i",str(caminho_video),"-c","copy",
               "-avoid_negative_ts","make_zero", str(dest)]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            log(f"  ✓ {nome_arq}")
            arquivos.append({"caminho": dest, "corte": corte})
        else:
            log(f"  ✗ Erro: {res.stderr[-100:]}", "ERRO")

    return arquivos

# ─── ETAPA 4: GERAR LEGENDA ASS ──────────────────────────

def gerar_ass(segmentos, inicio_corte, fim_corte, caminho_saida):
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
    def t2ass(s):
        h=int(s//3600); m=int((s%3600)//60); sc=s%60
        return f"{h}:{m:02d}:{sc:05.2f}"

    linhas = [header]
    for seg in segmentos:
        if seg["end"] <= inicio_corte or seg["start"] >= fim_corte:
            continue
        t_ini = max(0.0, seg["start"] - inicio_corte)
        t_fim = min(fim_corte - inicio_corte, seg["end"] - inicio_corte)
        texto = seg["text"].strip().replace("\n"," ")
        if len(texto) > 38:
            meio = len(texto)//2
            esp  = texto.rfind(" ", 0, meio)
            if esp > 0:
                texto = texto[:esp] + r"\N" + texto[esp+1:]
        linhas.append(f"Dialogue: 0,{t2ass(t_ini)},{t2ass(t_fim)},Default,,0,0,0,,{texto}")

    with open(caminho_saida,"w",encoding="utf-8") as f:
        f.write("\n".join(linhas))

# ─── ETAPA 5: PROCESSAR PARA TIKTOK + SHORTS ─────────────

def processar_corte(arquivo_corte, segmentos, pasta_saida, titulo_video):
    caminho_entrada = arquivo_corte["caminho"]
    corte           = arquivo_corte["corte"]
    inicio_corte    = float(corte["inicio"])
    fim_corte       = float(corte["fim"])

    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    ts          = datetime.now().strftime("%H%M%S")
    nome_saida  = f"pronto_{caminho_entrada.stem}_{ts}.mp4"
    txt_saida   = pasta_saida / f"pronto_{caminho_entrada.stem}_{ts}.txt"
    caminho_out = pasta_saida / nome_saida

    log(f"Processando para TikTok + Shorts: {caminho_entrada.name}", "PROC")

    with tempfile.TemporaryDirectory() as tmp:
        tmp      = Path(tmp)
        ass_path = tmp / "legendas.ass"
        gerar_ass(segmentos, inicio_corte, fim_corte, ass_path)

        ass_esc  = str(ass_path).replace("\\","/").replace(":","\\:")
        nome_esc = NOME_CANAL.replace("@","\\@")

        # 9:16 vertical | legendas queimadas | nome do canal
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            f"ass='{ass_esc}',"
            f"drawtext=text='{nome_esc}':fontcolor=white:fontsize=26:"
            "box=1:boxcolor=black@0.55:boxborderw=8:x=w-tw-20:y=24"
        )

        # Pitch imperceptível — muda fingerprint de áudio
        af = f"atempo={PITCH_VALOR},asetrate=44100*{PITCH_VALOR},aresample=44100"

        cmd = [
            "ffmpeg","-y","-i",str(caminho_entrada),
            "-vf",vf,"-af",af,
            "-c:v","libx264",
            "-crf",str(QUALIDADE_CRF),
            "-preset",VELOCIDADE_ENC,
            "-profile:v","high","-level","4.1",  # máxima compatibilidade
            "-pix_fmt","yuv420p",
            "-r","30",                            # 30fps padrão TikTok e Shorts
            "-movflags","+faststart",
            "-c:a","aac","-b:a","192k","-ar","44100",
            "-map_metadata","-1",                 # apaga todos os metadados
            "-metadata","title=",
            "-metadata","comment=",
            "-metadata","encoder=",
            str(caminho_out)
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            log(f"Erro FFmpeg: {res.stderr[-200:]}", "ERRO")
            return None, None, 0.0

        tam = caminho_out.stat().st_size / (1024*1024)
        log(f"✅ Pronto: {nome_saida} ({tam:.1f} MB)")

    # Gerar descrição com IA
    desc_info  = None
    custo_desc = 0.0
    if GERAR_DESCRICAO:
        log("IA gerando título + descrição + hashtags...", "IA")
        desc_info, custo_desc = ia_gerar_descricao(corte, titulo_video)
        if desc_info:
            hashtags_str = " ".join(desc_info.get("hashtags",[]))
            conteudo = (
                f"=== YOUTUBE SHORTS ===\n"
                f"TÍTULO:\n{desc_info.get('titulo_yt', corte.get('titulo',''))}\n\n"
                f"DESCRIÇÃO:\n{desc_info.get('descricao','')}\n\n"
                f"HASHTAGS:\n{hashtags_str}\n\n"
                f"=== TIKTOK ===\n"
                f"TÍTULO:\n{desc_info.get('titulo_tiktok', corte.get('titulo',''))}\n\n"
                f"DESCRIÇÃO:\n{desc_info.get('descricao','')}\n\n"
                f"HASHTAGS:\n{hashtags_str}\n\n"
                f"=== GERAL ===\n"
                f"GANCHO (primeiros 3s):\n{corte.get('gancho','')}\n"
                f"TIPO: {corte.get('tipo','—')} | DURAÇÃO: {fim_corte-inicio_corte:.0f}s\n"
            )
            txt_saida.write_text(conteudo, encoding="utf-8")
            log(f"📝 {txt_saida.name}")

    return caminho_out, (txt_saida if desc_info else None), custo_desc

# ─── PIPELINE PRINCIPAL ───────────────────────────────────

def pipeline(caminho_video, forcar=False):
    caminho_video = Path(caminho_video)

    if not caminho_video.exists():
        log(f"Arquivo não encontrado: {caminho_video}", "ERRO")
        sys.exit(1)

    if caminho_video.suffix.lower() not in EXTENSOES_VALIDAS:
        log(f"Formato não suportado: {caminho_video.suffix}", "ERRO")
        log(f"Formatos aceitos: {', '.join(EXTENSOES_VALIDAS)}")
        sys.exit(1)

    # Importar banco
    try:
        import banco
        banco.inicializar()
        usar_banco = True
    except ImportError:
        log("banco.py não encontrado — rodando sem banco", "AVISO")
        usar_banco = False

    titulo = caminho_video.stem.replace("_"," ").replace("-"," ")

    print("\n" + "═"*58)
    print("  PROCESSADOR DE VÍDEO → TIKTOK + YOUTUBE SHORTS")
    print("═"*58 + "\n")
    print(f"  Arquivo : {caminho_video.name}")

    verificar_deps()

    for p in [PASTA_CORTES, PASTA_PRONTOS]:
        Path(p).mkdir(exist_ok=True)

    # Verificar banco (duplicata)
    video_id = None
    if usar_banco and not forcar:
        # Usa o caminho como identificador único para vídeos locais
        vid_key  = f"local_{caminho_video.stem}"
        registro = banco.video_ja_processado(vid_key)
        if registro:
            print(f"\n⚠️  Este vídeo já foi processado anteriormente!")
            print(f"   Cortes : {registro['num_cortes']}")
            print(f"   Data   : {registro['criado_em']}")
            print(f"\n   Use --forcar para reprocessar mesmo assim.\n")
            cortes_existentes = banco.listar_cortes(video_id=registro["id"])
            if cortes_existentes:
                print("   Cortes existentes:")
                for c in cortes_existentes:
                    print(f"     [{c['numero']:02d}] {c['tipo']:6} | {c['duracao_s']:.0f}s | {c['status'].upper()} | {c['titulo']}")
            print()
            return []

    # ── Info do vídeo ────────────────────────────────────
    info = obter_info_video(caminho_video)
    print(f"  Duração : {int(info['duracao']//60)}min {int(info['duracao']%60)}s")
    print(f"  Resolução: {info['largura']}x{info['altura']} | {info['fps']}fps\n")

    if usar_banco:
        vid_key  = f"local_{caminho_video.stem}"
        video_id = banco.registrar_video(
            url=vid_key, titulo=titulo,
            duracao_s=info["duracao"], caminho_arquivo=str(caminho_video)
        )
        log(f"Vídeo registrado no banco (ID: {video_id})", "DB")

    # ── 1. Transcrição ───────────────────────────────────
    print("\n🎙  ETAPA 1: Transcrição com Whisper\n" + "─"*45)
    segmentos = transcrever(caminho_video)
    transcricao_texto = segmentos_para_texto(segmentos)

    if usar_banco and video_id:
        banco.marcar_transcrito(video_id)

    # ── 2. IA seleciona cortes ───────────────────────────
    print("\n🤖 ETAPA 2: IA selecionando melhores momentos\n" + "─"*45)
    cortes, custo_cortes = ia_selecionar_cortes(transcricao_texto, info["duracao"], titulo)

    if usar_banco and video_id:
        banco.atualizar_custo(video_id, custo_cortes)

    # Filtrar durações inválidas
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

    # ── 3. Cortar ────────────────────────────────────────
    print(f"\n✂️  ETAPA 3: Cortando {len(cortes_validos)} trechos\n" + "─"*45)
    arquivos_cortados = cortar_video(caminho_video, cortes_validos, PASTA_CORTES)

    # ── 4. Processar ─────────────────────────────────────
    print(f"\n🎬 ETAPA 4: Processando para TikTok + Shorts\n" + "─"*45)
    prontos          = []
    custo_desc_total = 0.0

    for i, arq in enumerate(arquivos_cortados, 1):
        video_out, txt_out, custo_desc = processar_corte(
            arq, segmentos, PASTA_PRONTOS, titulo
        )
        custo_desc_total += custo_desc

        if video_out:
            prontos.append((video_out, txt_out))
            if usar_banco and video_id:
                corte_id = banco.registrar_corte(
                    video_id=video_id, numero=i,
                    corte_info=arq["corte"],
                    caminho_video=video_out,
                    caminho_txt=txt_out,
                    desc_info=None
                )
                log(f"Corte {i} registrado no banco (ID: {corte_id})", "DB")

    if usar_banco and video_id:
        banco.atualizar_custo(video_id, custo_desc_total)
        custo_total = custo_cortes + custo_desc_total
        log(f"Custo total API: ${custo_total:.4f} (~R${custo_total*5.6:.2f})", "DB")

    # ── Resumo ───────────────────────────────────────────
    print("\n" + "═"*58)
    print(f"  ✅ CONCLUÍDO: {len(prontos)}/{len(cortes_validos)} vídeos prontos")
    print(f"  📁 Saída: {Path(PASTA_PRONTOS).resolve()}")
    if usar_banco:
        s = banco.stats()
        print(f"  🗄️  Banco: {s['total_videos']} vídeos | {s['total_cortes']} cortes | {s['postados']} postados")
    print("═"*58 + "\n")

    if prontos:
        print("Arquivos prontos para postar no TikTok e YouTube Shorts:\n")
        for video, txt in prontos:
            print(f"   🎥 {video.name}")
            if txt:
                print(f"   📝 {txt.name}  ← título, descrição e hashtags")
            print()

    return prontos

# ─── MODO PASTA ───────────────────────────────────────────

def processar_pasta(pasta, forcar=False):
    pasta    = Path(pasta)
    videos   = [f for f in pasta.iterdir() if f.suffix.lower() in EXTENSOES_VALIDAS]

    if not videos:
        log(f"Nenhum vídeo encontrado em '{pasta}'", "AVISO")
        log(f"Formatos aceitos: {', '.join(EXTENSOES_VALIDAS)}")
        return

    log(f"Encontrados {len(videos)} vídeo(s) em '{pasta}'")
    print("─"*50)

    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] {video.name}\n")
        pipeline(video, forcar=forcar)
        print("─"*50)

# ─── ENTRADA ──────────────────────────────────────────────

def main():
    global CHAVE_ANTHROPIC, MODELO_WHISPER

    parser = argparse.ArgumentParser(
        description="Vídeo local → TikTok + YouTube Shorts com IA"
    )
    parser.add_argument("--arquivo", help="Caminho do vídeo a processar")
    parser.add_argument("--pasta",   help="Pasta com vídeos para processar todos")
    parser.add_argument("--chave",   help="Chave API Anthropic")
    parser.add_argument("--modelo",  default=MODELO_WHISPER,
                        choices=["tiny","base","small","medium","large"],
                        help="Modelo Whisper para transcrição")
    parser.add_argument("--forcar",  action="store_true",
                        help="Reprocessa mesmo se já estiver no banco")
    args = parser.parse_args()

    if args.chave:  CHAVE_ANTHROPIC = args.chave
    if args.modelo: MODELO_WHISPER  = args.modelo

    if args.pasta:
        processar_pasta(args.pasta, forcar=args.forcar)

    elif args.arquivo:
        pipeline(args.arquivo, forcar=args.forcar)

    else:
        print("\n" + "═"*58)
        print("  PROCESSADOR DE VÍDEO → TIKTOK + YOUTUBE SHORTS")
        print("═"*58)
        arquivo = input("\n📁 Caminho do vídeo: ").strip().strip('"').strip("'")
        if not arquivo:
            print("Nenhum arquivo informado. Saindo.")
            sys.exit(1)
        pipeline(arquivo, forcar=args.forcar)

if __name__ == "__main__":
    main()