#!/usr/bin/env python3
"""
=======================================================
  GERADOR DE CONTEÚDO RELIGIOSO — TikTok + Shorts
=======================================================
  Gera automaticamente 4 formatos de vídeo originais:

  FORMATO 1 — Reflexão do dia         (~75–90s) ← monetização máxima
  FORMATO 2 — História bíblica/santo  (~70–85s) ← monetização máxima
  FORMATO 3 — Versículo do dia        (~60–65s) ← monetização base
  FORMATO 4 — Corte de podcast        (50–59s)  ← via youtube_para_shorts.py

  Distribuição por dia (padrão):
    • 2 vídeos longos (75–90s) — reflexão ou história
    • 1 vídeo médio (60–65s)   — versículo
    → maioria dos vídeos acima de 60s para maior RPM

  PIPELINE por vídeo:
  1. IA (Claude) gera o roteiro completo
  2. Voz de IA narra o roteiro (ElevenLabs ou gTTS gratuito)
  3. FFmpeg monta: vídeo de fundo + áudio + legenda + logo
  4. Salva pronto para postar + .txt com título/descrição/hashtags
  5. Registra no banco

  Uso:
    python gerador_conteudo.py                    (gera os vídeos do dia)
    python gerador_conteudo.py --formato reflexao
    python gerador_conteudo.py --formato historia
    python gerador_conteudo.py --formato versiculo
    python gerador_conteudo.py --quantidade 3
    python gerador_conteudo.py --tema "ansiedade e fé"
=======================================================
"""

import asyncio
import edge_tts
import os, sys, json, re, random, shutil, argparse, subprocess, tempfile
from pathlib import Path
from datetime import datetime
from logger_setup import get_logger
from retry import chamar_anthropic, chamar_elevenlabs
from telegram import notificar
try:
    from analytics import obter_config_otimizada
    _config_otimizada = obter_config_otimizada()
except Exception:
    _config_otimizada = {}

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════
#  CONFIGURAÇÕES — edite em config.py
# ═══════════════════════════════════════════════════════
from config import cfg

CHAVE_ANTHROPIC  = cfg.chave_anthropic
CHAVE_ELEVENLABS = cfg.chave_elevenlabs
MODELO_CLAUDE    = cfg.modelo_claude
PASTA_FUNDOS     = str(cfg.pasta_fundos)
PASTA_MUSICAS    = str(cfg.pasta_musicas)
PASTA_PRONTOS    = str(cfg.pasta_prontos)
PASTA_AUDIO_TEMP = str(cfg.pasta_audio_temp)
NOME_CANAL       = cfg.nome_canal
COR_LEGENDA      = cfg.cor_legenda
TAMANHO_FONT     = 22
QUALIDADE_CRF    = cfg.qualidade_crf
VELOCIDADE_ENC   = cfg.velocidade_enc
PITCH_VALOR      = cfg.pitch_valor
DURACAO_REFLEXAO  = cfg.duracao_reflexao
DURACAO_HISTORIA  = cfg.duracao_historia
DURACAO_VERSICULO = cfg.duracao_versiculo
VOLUME_MUSICA     = cfg.volume_musica
VOZ_ELEVENLABS_ID = cfg.voz_elevenlabs_id
VIDEOS_POR_DIA   = {"reflexao": 4, "historia": 4, "versiculo": 2}
# ═══════════════════════════════════════════════════════

CORES_ASS = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00"}

# Temas rotativos para variar o conteúdo
def _proximo_tema(tipo: str, lista: list) -> str:
    """
    Seleciona o próximo tema não usado recentemente via banco.
    Garante diversidade de conteúdo — nunca repete antes de esgotar o ciclo.
    """
    try:
        import banco as _banco
        _banco.inicializar()
        return _banco.proximo_tema_disponivel(tipo, lista)
    except Exception:
        # Fallback seguro se banco não disponível
        return random.choice(lista)


TEMAS_REFLEXAO = [
    "fé nos momentos difíceis", "propósito de vida", "gratidão e bênçãos",
    "superação pelo poder de Deus", "paz interior e ansiedade", "amor ao próximo",
    "perdão e libertação", "esperança na tribulação", "oração e intimidade com Deus",
    "cura interior e emocional", "família e proteção divina", "coragem para recomeçar",
    "confiança em Deus nos planos", "identidade em Cristo", "vitória espiritual",
]

TEMAS_HISTORIA = [
    "Davi e Golias", "José no Egito", "Moisés e o Mar Vermelho",
    "A parábola do filho pródigo", "Pedro caminhando sobre as águas",
    "A história de Jó", "Santa Teresinha do Menino Jesus",
    "São Francisco de Assis e os pobres", "A história de Esther",
    "O milagre das bodas de Caná", "A conversão de Paulo",
    "São Padre Pio e os milagres", "A história de Rute e Noemi",
    "Daniel na cova dos leões", "A ressurreição de Lázaro",
    "Santo Antônio e os milagres", "A história de Abraão e Isaque",
    "Maria Madalena e a redenção", "São João Bosco e os jovens",
    "A história de Gedeão",
]

VERSICULOS_TEMA = [
    "Filipenses 4:13", "Jeremias 29:11", "João 3:16", "Salmos 23",
    "Romanos 8:28", "Isaías 40:31", "Salmos 46:1", "Mateus 6:33",
    "Provérbios 3:5-6", "Salmos 121:1-2", "João 14:27", "Romanos 8:37",
    "Gálatas 2:20", "Efésios 6:10", "Salmos 91:1-2",
]

def log(msg, nivel="INFO"):
    hora = datetime.now().strftime("%H:%M:%S")
    p = {"INFO":"✓","ERRO":"✗","AVISO":"⚠","PROC":"→","IA":"🤖","DB":"🗄️"}
    print(f"[{hora}] {p.get(nivel,'·')} {msg}")
    if nivel == "ERRO":   logger.error(msg)
    elif nivel == "AVISO": logger.warning(msg)
    else:                  logger.info(msg)

# ─── VERIFICAÇÃO ─────────────────────────────────────────

def verificar_deps():
    erros = []
    if not shutil.which("ffmpeg"):
        erros.append("FFmpeg não instalado → https://ffmpeg.org/download.html")
    try:
        import anthropic
    except ImportError:
        erros.append("anthropic não instalado → pip install anthropic")
    if not CHAVE_ANTHROPIC:
        print("\n❌ Chave da API Anthropic não configurada.")
        print("   export ANTHROPIC_API_KEY=sua_chave")
        sys.exit(1)
    if erros:
        print("\n❌ Dependências faltando:\n")
        for e in erros: print(f"   • {e}")
        sys.exit(1)

    # Verificar voz disponível
    if CHAVE_ELEVENLABS:
        log("Voz: ElevenLabs (alta qualidade)")
    else:
        try:
            import gtts
            log("Voz: gTTS gratuito (para ElevenLabs: export ELEVENLABS_API_KEY=...)")
        except ImportError:
            erros.append("gtts não instalado → pip install gtts")

    log("Dependências OK")

# ─── ETAPA 1: IA GERA ROTEIRO ────────────────────────────

def calcular_palavras_alvo(duracao_min, duracao_max):
    """Calcula palavras necessárias para atingir a duração alvo.
    Média de fala em PT-BR: ~130 palavras/minuto."""
    media = (duracao_min + duracao_max) / 2
    return int(media / 60 * 130)

def ia_gerar_reflexao(tema=None, duracao=None):
    import anthropic
    if not tema:
        # Priorizar temas recomendados pela análise de performance
        temas_rec = _config_otimizada.get("temas_recomendados", [])
        if temas_rec and random.random() < 0.6:  # 60% chance de usar recomendado
            tema = _proximo_tema("reflexao", temas_rec + TEMAS_REFLEXAO)
        else:
            tema = _proximo_tema("reflexao", TEMAS_REFLEXAO)
    dur = duracao or DURACAO_REFLEXAO
    palavras = calcular_palavras_alvo(dur[0], dur[1])

    log(f"IA gerando reflexão sobre: '{tema}' (~{palavras} palavras)", "IA")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Crie uma reflexão espiritual cristã para TikTok/Shorts sobre o tema: "{tema}"

REQUISITOS:
- Exatamente {palavras} palavras (±10) — isso é crítico para a duração do vídeo
- Tom: íntimo, acolhedor, como um pastor falando com seu rebanho
- Começa com uma FRASE DE IMPACTO ou pergunta que prende atenção nos primeiros 3 segundos
- Desenvolve o tema com profundidade e exemplos práticos do dia a dia
- Inclui pelo menos 1 versículo bíblico encaixado naturalmente no texto
- Termina com uma declaração de fé poderosa ou chamada para ação espiritual
- Linguagem simples, acessível, sem palavras difíceis
- NÃO use títulos, subtítulos, bullets ou marcadores — texto corrido para narração

Responda SOMENTE com JSON puro:
{{"roteiro":"texto completo aqui","tema":"{tema}","versiculo_usado":"ref do versículo","titulo_yt":"Título YouTube (máx 80 chars com emoji)","titulo_tiktok":"Título TikTok (máx 60 chars)","descricao":"3 linhas com CTA","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE, max_tokens=2000,
        messages=[{"role":"user","content":prompt}]
    )
    custo = (resposta.usage.input_tokens*3 + resposta.usage.output_tokens*15) / 1_000_000
    texto = re.sub(r"```json|```","", resposta.content[0].text.strip()).strip()
    dados = json.loads(texto)
    dados["formato"]    = "reflexao"
    dados["custo_usd"]  = custo
    dados["duracao_alvo"] = dur
    return dados

def ia_gerar_historia(tema=None, duracao=None):
    import anthropic
    if not tema:
        temas_rec = _config_otimizada.get("temas_recomendados", [])
        if temas_rec and random.random() < 0.6:
            tema = _proximo_tema("historia", temas_rec + TEMAS_HISTORIA)
        else:
            tema = _proximo_tema("historia", TEMAS_HISTORIA)
    dur = duracao or DURACAO_HISTORIA
    palavras = calcular_palavras_alvo(dur[0], dur[1])

    log(f"IA gerando história: '{tema}' (~{palavras} palavras)", "IA")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Narre a história de "{tema}" para um vídeo TikTok/Shorts de conteúdo religioso.

REQUISITOS:
- Exatamente {palavras} palavras (±10) — crítico para duração do vídeo
- Estilo: narração cinematográfica, como um documentário bíblico
- Começa com uma frase de impacto que contextualiza o personagem/situação imediatamente
- Conta a história com emoção, detalhes vivos e linguagem atual
- Conecta a história ao dia a dia do espectador moderno
- Termina com uma lição aplicável à vida hoje
- NÃO use títulos, subtítulos ou marcadores — texto corrido para narração

Responda SOMENTE com JSON puro:
{{"roteiro":"texto completo aqui","tema":"{tema}","tipo":"bíblica ou santo","titulo_yt":"Título YouTube (máx 80 chars com emoji)","titulo_tiktok":"Título TikTok (máx 60 chars)","descricao":"3 linhas com CTA","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE, max_tokens=2000,
        messages=[{"role":"user","content":prompt}]
    )
    custo = (resposta.usage.input_tokens*3 + resposta.usage.output_tokens*15) / 1_000_000
    texto = re.sub(r"```json|```","", resposta.content[0].text.strip()).strip()
    dados = json.loads(texto)
    dados["formato"]      = "historia"
    dados["custo_usd"]    = custo
    dados["duracao_alvo"] = dur
    return dados

def ia_gerar_versiculo(versiculo=None, duracao=None):
    import anthropic
    if not versiculo:
        versiculo = _proximo_tema("versiculo", VERSICULOS_TEMA)
    dur = duracao or DURACAO_VERSICULO
    palavras = calcular_palavras_alvo(dur[0], dur[1])

    log(f"IA gerando versículo: '{versiculo}' (~{palavras} palavras)", "IA")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt  = f"""Crie um vídeo de versículo do dia sobre "{versiculo}" para TikTok/Shorts.

REQUISITOS:
- Exatamente {palavras} palavras (±10) — crítico para duração
- Começa lendo o versículo de forma pausada e impactante
- Explica o significado profundo em linguagem simples e atual
- Dá um exemplo prático de como aplicar esse versículo hoje
- Termina com uma oração curta ou declaração de fé
- NÃO use títulos ou marcadores — texto corrido para narração

Responda SOMENTE com JSON puro:
{{"roteiro":"texto completo aqui","versiculo":"{versiculo}","titulo_yt":"Título YouTube (máx 80 chars com emoji)","titulo_tiktok":"Título TikTok (máx 60 chars)","descricao":"3 linhas com CTA","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE, max_tokens=1500,
        messages=[{"role":"user","content":prompt}]
    )
    custo = (resposta.usage.input_tokens*3 + resposta.usage.output_tokens*15) / 1_000_000
    texto = re.sub(r"```json|```","", resposta.content[0].text.strip()).strip()
    dados = json.loads(texto)
    dados["formato"]      = "versiculo"
    dados["custo_usd"]    = custo
    dados["duracao_alvo"] = dur
    return dados

# ─── ETAPA 2: GERAR ÁUDIO ────────────────────────────────

def gerar_audio_elevenlabs(roteiro, caminho_saida):
    """Voz de alta qualidade — requer ELEVENLABS_API_KEY"""
    import requests
    log("Gerando voz com ElevenLabs...", "PROC")

    url  = f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ_ELEVENLABS_ID}"
    headers = {
        "xi-api-key":   CHAVE_ELEVENLABS,
        "Content-Type": "application/json"
    }
    body = {
        "text": roteiro,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability":        0.5,
            "similarity_boost": 0.8,
            "style":            0.3,
            "use_speaker_boost": True
        }
    }
    res = chamar_elevenlabs(requests.post, url, headers=headers, json=body)
    if res.status_code != 200:
        raise RuntimeError(
            f"Erro ElevenLabs: {res.text[:200]}"
        )

    with open(caminho_saida, "wb") as f:
        f.write(res.content)
    log(f"Áudio gerado: {Path(caminho_saida).stat().st_size/1024:.0f} KB")
    return True

def gerar_audio_gtts(roteiro, caminho_saida):
    """Voz gratuita — sem necessidade de API key"""
    from gtts import gTTS
    log("Gerando voz com gTTS (gratuito)...", "PROC")
    tts = gTTS(text=roteiro, lang="pt", slow=False)
    tts.save(str(caminho_saida))
    log(f"Áudio gerado: {Path(caminho_saida).stat().st_size/1024:.0f} KB")
    return True

async def _edge_tts_async(texto, caminho_saida):
    communicate = edge_tts.Communicate(
        texto,
        voice="pt-BR-AntonioNeural",
        rate="+5%"
    )

    await communicate.save(str(caminho_saida))


def gerar_audio_edge(roteiro, caminho_saida):
    """Voz gratuita usando Edge TTS"""

    log("Gerando voz com Edge TTS...", "PROC")

    asyncio.run(
        _edge_tts_async(
            roteiro,
            caminho_saida
        )
    )

    log(
        f"Áudio gerado: {Path(caminho_saida).stat().st_size/1024:.0f} KB"
    )

    return True

def gerar_audio(roteiro, caminho_saida):
    """
    Prioridade:

    1 - ElevenLabs
    2 - Edge TTS
    3 - gTTS
    """

    if CHAVE_ELEVENLABS:

        try:
            log("Tentando ElevenLabs...", "PROC")
            return gerar_audio_elevenlabs(
                roteiro,
                caminho_saida
            )

        except Exception as e:
            log(
                f"ElevenLabs indisponível ({e})",
                "AVISO"
            )

    try:
        log("Alternando para Edge TTS...", "PROC")
        return gerar_audio_edge(
            roteiro,
            caminho_saida
        )

    except Exception as e:
        log(
            f"Edge TTS falhou ({e})",
            "AVISO"
        )

    log("Alternando para gTTS...", "PROC")

    return gerar_audio_gtts(
        roteiro,
        caminho_saida
    )


def obter_duracao_audio(caminho):
    cmd = ["ffprobe","-v","quiet","-show_entries","format=duration",
           "-of","json", str(caminho)]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    try:
        return float(json.loads(res.stdout)["format"]["duration"])
    except Exception:
        return 0.0

# ─── ETAPA 3: GERAR LEGENDA ASS ──────────────────────────

def roteiro_para_ass(roteiro, duracao_audio, caminho_saida):
    """Gera legenda ASS sincronizada estimando tempo por palavra"""
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

    # Quebrar em frases curtas para legenda
    frases = re.split(r'(?<=[.!?,;])\s+', roteiro.strip())
    frases = [f.strip() for f in frases if f.strip()]

    palavras_total = sum(len(f.split()) for f in frases)
    seg_por_palavra = duracao_audio / max(palavras_total, 1)

    linhas  = [header]
    t_atual = 0.2  # pequeno delay inicial

    for frase in frases:
        palavras_frase = len(frase.split())
        duracao_frase  = palavras_frase * seg_por_palavra

        # Quebrar frases longas em 2 linhas
        if len(frase) > 45:
            meio = len(frase)//2
            esp  = frase.rfind(" ", 0, meio)
            if esp > 0:
                frase = frase[:esp] + r"\N" + frase[esp+1:]

        t_fim = min(t_atual + duracao_frase, duracao_audio - 0.1)
        linhas.append(f"Dialogue: 0,{t2ass(t_atual)},{t2ass(t_fim)},Default,,0,0,0,,{frase}")
        t_atual = t_fim + 0.05

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

# ─── ETAPA 4: MONTAR VÍDEO ───────────────────────────────

def obter_fundo_aleatorio():
    """Retorna um vídeo de fundo aleatório da pasta fundos/ ou subpastas."""
    pasta = Path(PASTA_FUNDOS)
    if pasta.exists():
        # Buscar na raiz E em subpastas (fundos/ceu/, fundos/natureza/, etc.)
        videos = (list(pasta.glob("*.mp4"))   + list(pasta.glob("*.mov")) +
                  list(pasta.glob("**/*.mp4")) + list(pasta.glob("**/*.mov")))
        # Remover duplicatas mantendo ordem aleatória
        videos = list(dict.fromkeys(videos))
        if videos:
            return random.choice(videos)

    # Sem fundo disponível — gera fundo preto
    return None

def obter_musica_aleatoria():
    """Retorna uma música instrumental aleatória"""
    pasta = Path(PASTA_MUSICAS)
    if pasta.exists():
        musicas = list(pasta.glob("*.mp3")) + list(pasta.glob("*.wav")) + list(pasta.glob("*.m4a"))
        if musicas:
            return random.choice(musicas)
    return None

def montar_video(dados_roteiro, caminho_audio, pasta_saida):
    """Monta o vídeo final com fundo + áudio + legenda + logo"""
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    duracao = obter_duracao_audio(caminho_audio)
    if duracao < 1:
        log("Áudio inválido ou muito curto.", "ERRO")
        return None, None

    log(f"Duração do áudio: {duracao:.1f}s", "PROC")

    ts        = datetime.now().strftime("%H%M%S")
    fmt       = dados_roteiro.get("formato","video")
    nome_base = f"{fmt}_{ts}"
    saida_mp4 = pasta_saida / f"{nome_base}.mp4"
    saida_txt = pasta_saida / f"{nome_base}.txt"

    fundo   = obter_fundo_aleatorio()
    musica  = obter_musica_aleatoria()

    with tempfile.TemporaryDirectory() as tmp:
        tmp      = Path(tmp)
        ass_path = tmp / "legenda.ass"
        roteiro_para_ass(dados_roteiro["roteiro"], duracao, ass_path)

        if cfg.fundo_ia:  # fundo IA (ComfyUI/LTX) composto só com FFmpeg; None => fundos atuais
            from fundos_ia import obter_fundo_ia
            fundo = obter_fundo_ia(duracao, tmp) or fundo

        ass_esc  = str(ass_path).replace("\\","/").replace(":","\\:")
        nome_esc = NOME_CANAL.replace("@","\\@")

        # ── Montar inputs ────────────────────────────────
        inputs = []

        if fundo:
            # Loop do vídeo de fundo se for mais curto que o áudio
            inputs += ["-stream_loop","-1","-i",str(fundo)]
            log(f"Fundo: {fundo.name}", "PROC")
        else:
            # Fundo preto gerado
            inputs += ["-f","lavfi","-i",f"color=c=black:s=1080x1920:r=30"]
            log("Fundo: preto (coloque vídeos em fundos/)", "AVISO")

        inputs += ["-i", str(caminho_audio)]

        if musica:
            inputs += ["-stream_loop","-1","-i",str(musica)]
            log(f"Música: {musica.name}", "PROC")

        # ── Filtros de vídeo ─────────────────────────────
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"ass='{ass_esc}',"
            f"drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='{nome_esc}':fontcolor=white:fontsize=26:"
            "box=1:boxcolor=black@0.55:boxborderw=8:x=w-tw-20:y=24"
        )

        # ── Filtros de áudio ─────────────────────────────
        if musica:
            # Mix narração + música de fundo
            af = (
                f"[1:a]atempo={PITCH_VALOR},asetrate=44100*{PITCH_VALOR},aresample=44100[narr];"
                f"[2:a]aloop=loop=-1:size=44100*300,volume={VOLUME_MUSICA}[mus];"
                "[narr][mus]amix=inputs=2:duration=first[aout]"
            )
            map_audio = "[aout]"
        else:
            af = f"[1:a]atempo={PITCH_VALOR},asetrate=44100*{PITCH_VALOR},aresample=44100[aout]"
            map_audio = "[aout]"

        # ── Comando FFmpeg ───────────────────────────────
        cmd = (
            ["ffmpeg","-y"] +
            inputs +
            ["-t", str(duracao + 0.5)] +  # duração exata do áudio + buffer
            ["-vf", vf] +
            ["-filter_complex", af] +
            ["-map","0:v","-map",map_audio] +
            ["-c:v","libx264","-crf",str(QUALIDADE_CRF),
             "-preset",VELOCIDADE_ENC,
             "-profile:v","high","-level","4.1",
             "-pix_fmt","yuv420p","-r","30",
             "-movflags","+faststart",
             "-c:a","aac","-b:a","192k","-ar","44100",
             "-map_metadata","-1",
             "-metadata","title=","-metadata","comment=","-metadata","encoder=",
             str(saida_mp4)]
        )

        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)

        if res.returncode != 0:
            log(f"Erro FFmpeg (codigo {res.returncode}):\n{res.stderr[-6000:]}", "ERRO")
            return None, None

        tam = saida_mp4.stat().st_size / (1024*1024)
        dur_final = obter_duracao_audio(saida_mp4)
        log(f"✅ Vídeo pronto: {saida_mp4.name} ({tam:.1f}MB | {dur_final:.1f}s)")

    # ── Salvar .txt com título/descrição/hashtags ────────
    hashtags_str = " ".join(dados_roteiro.get("hashtags",[]))
    conteudo_txt = (
        f"=== YOUTUBE SHORTS ===\n"
        f"TÍTULO:\n{dados_roteiro.get('titulo_yt','')}\n\n"
        f"DESCRIÇÃO:\n{dados_roteiro.get('descricao','')}\n\n"
        f"HASHTAGS:\n{hashtags_str}\n\n"
        f"=== TIKTOK ===\n"
        f"TÍTULO:\n{dados_roteiro.get('titulo_tiktok','')}\n\n"
        f"DESCRIÇÃO:\n{dados_roteiro.get('descricao','')}\n\n"
        f"HASHTAGS:\n{hashtags_str}\n\n"
        f"=== INFO ===\n"
        f"FORMATO: {dados_roteiro.get('formato','')}\n"
        f"DURAÇÃO: {dur_final:.1f}s\n"
        f"TEMA: {dados_roteiro.get('tema') or dados_roteiro.get('versiculo','')}\n"
    )
    saida_txt.write_text(conteudo_txt, encoding="utf-8")
    log(f"📝 {saida_txt.name}")

    return saida_mp4, saida_txt

# ─── PIPELINE POR FORMATO ────────────────────────────────

def gerar_video(formato, tema=None, duracao=None):
    """Pipeline completo para um único vídeo"""

    # Importar banco se disponível
    usar_banco = False
    try:
        import banco
        banco.inicializar()
        usar_banco = True
    except ImportError:
        pass

    Path(PASTA_AUDIO_TEMP).mkdir(exist_ok=True)
    Path(PASTA_PRONTOS).mkdir(exist_ok=True)

    log(f"Gerando vídeo: {formato.upper()}", "PROC")
    print("─"*50)

    # 1. IA gera roteiro
    custo_total = 0.0
    if formato == "reflexao":
        dados = ia_gerar_reflexao(tema=tema, duracao=duracao)
    elif formato == "historia":
        dados = ia_gerar_historia(tema=tema, duracao=duracao)
    elif formato == "versiculo":
        dados = ia_gerar_versiculo(versiculo=tema, duracao=duracao)
    else:
        log(f"Formato desconhecido: {formato}", "ERRO")
        return None, None

    custo_total += dados.get("custo_usd", 0)
    palavras = len(dados["roteiro"].split())
    log(f"Roteiro: {palavras} palavras | custo: ${dados['custo_usd']:.4f}")

    # 2. Gerar áudio
    ts           = datetime.now().strftime("%H%M%S")
    audio_path   = Path(PASTA_AUDIO_TEMP) / f"audio_{formato}_{ts}.mp3"
    ok           = gerar_audio(dados["roteiro"], audio_path)
    if not ok:
        log("Falha ao gerar áudio.", "ERRO")
        return None, None

    # 3. Montar vídeo
    video_out, txt_out = montar_video(dados, audio_path, PASTA_PRONTOS)

    # Limpar áudio temp
    if audio_path.exists():
        audio_path.unlink()

    if video_out and usar_banco:
        vid_id = banco.registrar_video(
            url=f"gerado_{formato}_{ts}",
            titulo=dados.get("titulo_yt",""),
            duracao_s=obter_duracao_audio(video_out),
            caminho_arquivo=str(video_out)
        )
        banco.registrar_corte(
            video_id=vid_id, numero=1,
            corte_info={
                "categoria": "ia",
                "tipo":   formato,
                "titulo": dados.get("titulo_yt",""),
                "gancho": dados["roteiro"].split(".")[0][:80],
                "inicio": 0,
                "fim":    obter_duracao_audio(video_out)
            },
            caminho_video=video_out,
            caminho_txt=txt_out,
            desc_info=dados
        )
        log(f"Registrado no banco", "DB")

    return video_out, txt_out

# ─── PIPELINE DO DIA ─────────────────────────────────────

def gerar_videos_do_dia(formatos=None, quantidade=None):
    verificar_deps()

    # Monta automaticamente a fila de vídeos do dia
    if formatos:
        formatos_usar = formatos
    else:
        formatos_usar = []

        for formato, qtd in VIDEOS_POR_DIA.items():
            formatos_usar.extend([formato] * qtd)

        # embaralha para não gerar vários iguais em sequência
        random.shuffle(formatos_usar)

    # caso o usuário peça uma quantidade específica
    if quantidade:
        formatos_usar = formatos_usar[:quantidade]

    print("\n" + "═"*58)
    print("  GERADOR DE CONTEÚDO RELIGIOSO")
    print(f"  {len(formatos_usar)} vídeo(s) para gerar hoje")
    print("═"*58 + "\n")

    # Mostrar distribuição de duração
    duracoes = {
        "reflexao":  f"{DURACAO_REFLEXAO[0]}–{DURACAO_REFLEXAO[1]}s",
        "historia":  f"{DURACAO_HISTORIA[0]}–{DURACAO_HISTORIA[1]}s",
        "versiculo": f"{DURACAO_VERSICULO[0]}–{DURACAO_VERSICULO[1]}s",
    }
    longos  = sum(1 for f in formatos_usar if f in ["reflexao","historia"])
    medios  = sum(1 for f in formatos_usar if f == "versiculo")
    print(f"  Distribuição: {longos} longo(s) >60s | {medios} médio(s) =60s")
    print(f"  Pasta de saída: {Path(PASTA_PRONTOS).resolve()}\n")

    prontos     = []
    custo_total = 0.0

    for i, fmt in enumerate(formatos_usar, 1):
        print(f"\n[{i}/{len(formatos_usar)}] {fmt.upper()} ({duracoes.get(fmt,'?')})")
        video, txt = gerar_video(fmt)
        if video:
            prontos.append((video, txt, fmt))

    print("\n" + "═"*58)
    print(f"  ✅ {len(prontos)}/{len(formatos_usar)} vídeos gerados")
    print(f"  📁 {Path(PASTA_PRONTOS).resolve()}")
    print("═"*58 + "\n")

    if prontos:
        print("Vídeos prontos:\n")
        for v, t, f in prontos:
            dur = obter_duracao_audio(v)
            monetizavel = "✅ monetizável" if dur >= 60 else "⚠️ abaixo de 60s"
            print(f"  🎥 {v.name} ({dur:.0f}s) {monetizavel}")
            if t:
                print(f"  📝 {t.name}")
            print()

    # Notificar conclusão
    custo_total_local = sum(
        d.get("custo_usd", 0) for d in [{}]  # placeholder
    )
    notificar.pipeline_concluido(
        origem="Gerador de Conteúdo",
        total=len(formatos_usar),
        sucesso=len(prontos),
    )
    return prontos

# ─── CLI ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gerador de conteúdo religioso — TikTok + YouTube Shorts"
    )
    parser.add_argument("--formato",    choices=["reflexao","historia","versiculo"],
                        help="Gerar apenas um formato específico")
    parser.add_argument("--tema",       help="Tema ou versículo específico")
    parser.add_argument("--quantidade", type=int,
                        help="Quantidade total de vídeos a gerar")
    parser.add_argument("--longo",      action="store_true",
                        help="Gerar apenas vídeos longos (reflexão + história)")
    args = parser.parse_args()

    if args.longo:
        gerar_videos_do_dia(formatos=["reflexao","historia","reflexao"])
    elif args.formato:
        verificar_deps()
        gerar_video(args.formato, tema=args.tema)
    else:
        formatos = None
        if args.quantidade:
            # Mais longos quando quantidade é maior
            base = ["reflexao","historia","versiculo"]
            formatos = None  # usa distribuição padrão
        gerar_videos_do_dia(quantidade=args.quantidade)

if __name__ == "__main__":
    main()