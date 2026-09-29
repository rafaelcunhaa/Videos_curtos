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

import argparse
import asyncio
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import edge_tts
import requests

import banco
from config import cfg
from constantes import CORES_ASS
from logger_setup import get_logger
from retry import chamar_anthropic, chamar_elevenlabs
from telegram import notificar

try:
    from gtts import gTTS
except ImportError:
    gTTS = None
try:
    from analytics import obter_config_otimizada

    _config_otimizada = obter_config_otimizada()
except Exception:
    _config_otimizada = {}

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════
#  CONFIGURAÇÕES — edite em config.py
# ═══════════════════════════════════════════════════════

CHAVE_ANTHROPIC = cfg.chave_anthropic
CHAVE_ELEVENLABS = cfg.chave_elevenlabs
MODELO_CLAUDE = cfg.modelo_claude
PASTA_FUNDOS = str(cfg.pasta_fundos)
PASTA_MUSICAS = str(cfg.pasta_musicas)
PASTA_PRONTOS = str(cfg.pasta_prontos)
PASTA_AUDIO_TEMP = str(cfg.pasta_audio_temp)
NOME_CANAL = cfg.nome_canal
COR_LEGENDA = cfg.cor_legenda
TAMANHO_FONT = 22
QUALIDADE_CRF = cfg.qualidade_crf
VELOCIDADE_ENC = cfg.velocidade_enc
PITCH_VALOR = cfg.pitch_valor
DURACAO_REFLEXAO = cfg.duracao_reflexao
DURACAO_HISTORIA = cfg.duracao_historia
DURACAO_VERSICULO = cfg.duracao_versiculo
VOLUME_MUSICA = cfg.volume_musica
VOZ_ELEVENLABS_ID = cfg.voz_elevenlabs_id
VIDEOS_POR_DIA = {"reflexao": 4, "historia": 4, "versiculo": 2}
# ═══════════════════════════════════════════════════════

# CORES_ASS agora vem de constantes.py


# Temas rotativos para variar o conteúdo
def _proximo_tema(tipo: str, lista: list) -> str:
    """
    Seleciona o próximo tema não usado recentemente via banco.
    Garante diversidade de conteúdo — nunca repete antes de esgotar o ciclo.
    """
    try:
        banco.inicializar()
        return banco.proximo_tema_disponivel(tipo, lista)
    except Exception:
        # Fallback seguro se banco não disponível
        return random.choice(lista)


TEMAS_REFLEXAO = [
    "fé nos momentos difíceis",
    "propósito de vida",
    "gratidão e bênçãos",
    "superação pelo poder de Deus",
    "paz interior e ansiedade",
    "amor ao próximo",
    "perdão e libertação",
    "esperança na tribulação",
    "oração e intimidade com Deus",
    "cura interior e emocional",
    "família e proteção divina",
    "coragem para recomeçar",
    "confiança em Deus nos planos",
    "identidade em Cristo",
    "vitória espiritual",
]

TEMAS_HISTORIA = [
    "Davi e Golias",
    "José no Egito",
    "Moisés e o Mar Vermelho",
    "A parábola do filho pródigo",
    "Pedro caminhando sobre as águas",
    "A história de Jó",
    "Santa Teresinha do Menino Jesus",
    "São Francisco de Assis e os pobres",
    "A história de Esther",
    "O milagre das bodas de Caná",
    "A conversão de Paulo",
    "São Padre Pio e os milagres",
    "A história de Rute e Noemi",
    "Daniel na cova dos leões",
    "A ressurreição de Lázaro",
    "Santo Antônio e os milagres",
    "A história de Abraão e Isaque",
    "Maria Madalena e a redenção",
    "São João Bosco e os jovens",
    "A história de Gedeão",
]

VERSICULOS_TEMA = [
    "Filipenses 4:13",
    "Jeremias 29:11",
    "João 3:16",
    "Salmos 23",
    "Romanos 8:28",
    "Isaías 40:31",
    "Salmos 46:1",
    "Mateus 6:33",
    "Provérbios 3:5-6",
    "Salmos 121:1-2",
    "João 14:27",
    "Romanos 8:37",
    "Gálatas 2:20",
    "Efésios 6:10",
    "Salmos 91:1-2",
]


def log(msg, nivel="INFO"):
    hora = datetime.now().strftime("%H:%M:%S")
    p = {"INFO": "✓", "ERRO": "✗", "AVISO": "⚠", "PROC": "→", "IA": "🤖", "DB": "🗄️"}
    print(f"[{hora}] {p.get(nivel,'·')} {msg}")
    if nivel == "ERRO":
        logger.error(msg)
    elif nivel == "AVISO":
        logger.warning(msg)
    else:
        logger.info(msg)


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
        for e in erros:
            print(f"   • {e}")
        sys.exit(1)

    # Verificar voz disponível
    if CHAVE_ELEVENLABS:
        log("Voz: ElevenLabs (alta qualidade)")
    else:
        if gTTS:
            log("Voz: gTTS gratuito (para ElevenLabs: export ELEVENLABS_API_KEY=...)")
        else:
            erros.append("gtts não instalado → pip install gtts")

    log("Dependências OK")


# ─── ETAPA 1: IA GERA ROTEIRO ────────────────────────────


def calcular_palavras_alvo(duracao_min: int, duracao_max: int) -> int:
    """Calcula palavras necessárias para atingir a duração alvo.
    Média de fala em PT-BR: ~130 palavras/minuto."""
    media = (duracao_min + duracao_max) / 2
    return int(media / 60 * 130)


def _proximo_numero_serie(formato: str) -> int:
    """Retorna o próximo número de série sem tornar o banco obrigatório."""
    try:
        import banco

        cortes = banco.listar_cortes()
        return 1 + sum(1 for corte in cortes if corte.get("tipo") == formato)
    except Exception:
        return 1


def _normalizar_engajamento(dados: dict, formato: str, tema: str) -> dict:
    """Completa campos de engajamento sem confiar cegamente na resposta da IA."""
    numero = dados.get("numero_serie") or _proximo_numero_serie(formato)
    try:
        numero = max(1, int(numero))
    except (TypeError, ValueError):
        numero = _proximo_numero_serie(formato)
    gancho = str(dados.get("gancho") or "Você precisava ouvir isso hoje?").strip()
    opcoes = dados.get("gancho_opcoes")
    if not isinstance(opcoes, list) or len(opcoes) < 3:
        opcoes = [gancho, "Mas existe um detalhe que quase ninguém percebe...", "E se Deus estiver falando com você agora?"]
    dados.update(
        {
            "formato": formato,
            "tema": dados.get("tema") or dados.get("versiculo") or tema,
            "gancho": gancho,
            "gancho_opcoes": [str(opcao).strip() for opcao in opcoes[:3]],
            "numero_serie": numero,
            "serie": str(dados.get("serie") or formato.upper()),
            "cta_video": str(dados.get("cta_video") or "Comente AMÉM se essa mensagem falou com você."),
            "cta_comentario": str(dados.get("cta_comentario") or "Qual tema você quer ver no próximo vídeo?"),
        }
    )
    return dados


def ia_gerar_reflexao(
    tema: Optional[str] = None, duracao: Optional[tuple] = None
) -> dict:
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
    padrao_gancho = _config_otimizada.get("padrao_gancho", "pergunta ou contraste")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt = f"""Crie uma reflexão espiritual cristã para TikTok/Shorts sobre o tema: "{tema}"

REQUISITOS:
- Exatamente {palavras} palavras (±10) — isso é crítico para a duração do vídeo
- Tom: íntimo, acolhedor, como um pastor falando com seu rebanho
- Começa com uma FRASE DE IMPACTO ou pergunta que prende atenção nos primeiros 3 segundos
- Priorize este padrão de gancho quando aplicável: {padrao_gancho}
- Desenvolve o tema com profundidade e exemplos práticos do dia a dia
- Inclui pelo menos 1 versículo bíblico encaixado naturalmente no texto
- Termina com uma declaração de fé poderosa ou chamada para ação espiritual
- Linguagem simples, acessível, sem palavras difíceis
- NÃO use títulos, subtítulos, bullets ou marcadores — texto corrido para narração
- A primeira frase deve ser o gancho; não comece com saudação ou introdução genérica
- Termine com o CTA exatamente no final do roteiro

Responda SOMENTE com JSON puro:
{{"roteiro":"texto completo aqui começando pelo gancho e terminando pelo CTA","gancho":"gancho principal","gancho_opcoes":["opção 1","opção 2","opção 3"],"tema":"{tema}","versiculo_usado":"ref do versículo","serie":"REFLEXAO","numero_serie":1,"cta_video":"CTA curto para aparecer no vídeo","cta_comentario":"pergunta para comentários","titulo_yt":"Título YouTube (máx 80 chars com emoji)","titulo_tiktok":"Título TikTok (máx 60 chars)","descricao":"3 linhas com CTA","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    custo = (
        resposta.usage.input_tokens * 3 + resposta.usage.output_tokens * 15
    ) / 1_000_000
    texto = re.sub(r"```json|```", "", resposta.content[0].text.strip()).strip()
    dados = json.loads(texto)
    dados = _normalizar_engajamento(dados, "reflexao", tema)
    dados["transparencia_ia"] = bool(getattr(cfg, "mostrar_transparencia_ia", False))
    dados["custo_usd"] = custo
    dados["duracao_alvo"] = dur
    return dados


def ia_gerar_historia(
    tema: Optional[str] = None, duracao: Optional[tuple] = None
) -> dict:
    if not tema:
        temas_rec = _config_otimizada.get("temas_recomendados", [])
        if temas_rec and random.random() < 0.6:
            tema = _proximo_tema("historia", temas_rec + TEMAS_HISTORIA)
        else:
            tema = _proximo_tema("historia", TEMAS_HISTORIA)
    dur = duracao or DURACAO_HISTORIA
    palavras = calcular_palavras_alvo(dur[0], dur[1])

    log(f"IA gerando história: '{tema}' (~{palavras} palavras)", "IA")
    padrao_gancho = _config_otimizada.get("padrao_gancho", "pergunta ou contraste")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt = f"""Narre a história de "{tema}" para um vídeo TikTok/Shorts de conteúdo religioso.

REQUISITOS:
- Exatamente {palavras} palavras (±10) — crítico para duração do vídeo
- Estilo: narração cinematográfica, como um documentário bíblico
- Começa com uma frase de impacto que contextualiza o personagem/situação imediatamente
- Priorize este padrão de gancho quando aplicável: {padrao_gancho}
- Conta a história com emoção, detalhes vivos e linguagem atual
- Conecta a história ao dia a dia do espectador moderno
- Termina com uma lição aplicável à vida hoje
- NÃO use títulos, subtítulos ou marcadores — texto corrido para narração
- A primeira frase deve ser um gancho visual ou uma pergunta; termine com CTA

Responda SOMENTE com JSON puro:
{{"roteiro":"texto completo aqui começando pelo gancho e terminando pelo CTA","gancho":"gancho principal","gancho_opcoes":["opção 1","opção 2","opção 3"],"tema":"{tema}","tipo":"bíblica ou santo","serie":"HISTORIA","numero_serie":1,"cta_video":"CTA curto para aparecer no vídeo","cta_comentario":"pergunta para comentários","titulo_yt":"Título YouTube (máx 80 chars com emoji)","titulo_tiktok":"Título TikTok (máx 60 chars)","descricao":"3 linhas com CTA","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    custo = (
        resposta.usage.input_tokens * 3 + resposta.usage.output_tokens * 15
    ) / 1_000_000
    texto = re.sub(r"```json|```", "", resposta.content[0].text.strip()).strip()
    dados = json.loads(texto)
    dados = _normalizar_engajamento(dados, "historia", tema)
    dados["transparencia_ia"] = bool(getattr(cfg, "mostrar_transparencia_ia", False))
    dados["custo_usd"] = custo
    dados["duracao_alvo"] = dur
    return dados


def ia_gerar_versiculo(
    versiculo: Optional[str] = None, duracao: Optional[tuple] = None
) -> dict:
    if not versiculo:
        versiculo = _proximo_tema("versiculo", VERSICULOS_TEMA)
    dur = duracao or DURACAO_VERSICULO
    palavras = calcular_palavras_alvo(dur[0], dur[1])

    log(f"IA gerando versículo: '{versiculo}' (~{palavras} palavras)", "IA")
    padrao_gancho = _config_otimizada.get("padrao_gancho", "pergunta ou contraste")

    cliente = anthropic.Anthropic(api_key=CHAVE_ANTHROPIC)
    prompt = f"""Crie um vídeo de versículo do dia sobre "{versiculo}" para TikTok/Shorts.

REQUISITOS:
- Exatamente {palavras} palavras (±10) — crítico para duração
- Começa lendo o versículo de forma pausada e impactante
- Priorize este padrão de gancho quando aplicável: {padrao_gancho}
- Explica o significado profundo em linguagem simples e atual
- Dá um exemplo prático de como aplicar esse versículo hoje
- Termina com uma oração curta ou declaração de fé
- NÃO use títulos ou marcadores — texto corrido para narração
- Comece com um gancho antes da explicação e termine com CTA

Responda SOMENTE com JSON puro:
{{"roteiro":"texto completo aqui começando pelo gancho e terminando pelo CTA","gancho":"gancho principal","gancho_opcoes":["opção 1","opção 2","opção 3"],"versiculo":"{versiculo}","serie":"VERSICULO","numero_serie":1,"cta_video":"CTA curto para aparecer no vídeo","cta_comentario":"pergunta para comentários","titulo_yt":"Título YouTube (máx 80 chars com emoji)","titulo_tiktok":"Título TikTok (máx 60 chars)","descricao":"3 linhas com CTA","hashtags":["#tag1","#tag2","#tag3","#tag4","#tag5","#tag6","#tag7","#tag8","#tag9","#tag10"]}}"""

    resposta = chamar_anthropic(
        cliente.messages.create,
        model=MODELO_CLAUDE,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    custo = (
        resposta.usage.input_tokens * 3 + resposta.usage.output_tokens * 15
    ) / 1_000_000
    texto = re.sub(r"```json|```", "", resposta.content[0].text.strip()).strip()
    dados = json.loads(texto)
    dados = _normalizar_engajamento(dados, "versiculo", versiculo)
    dados["transparencia_ia"] = bool(getattr(cfg, "mostrar_transparencia_ia", False))
    dados["custo_usd"] = custo
    dados["duracao_alvo"] = dur
    return dados


# ─── ETAPA 2: GERAR ÁUDIO ────────────────────────────────


def gerar_audio_elevenlabs(roteiro: str, caminho_saida: Path) -> bool:
    """Voz de alta qualidade — requer ELEVENLABS_API_KEY"""
    log("Gerando voz com ElevenLabs...", "PROC")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ_ELEVENLABS_ID}"
    headers = {"xi-api-key": CHAVE_ELEVENLABS, "Content-Type": "application/json"}
    body = {
        "text": roteiro,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }
    res = chamar_elevenlabs(requests.post, url, headers=headers, json=body)
    if res.status_code != 200:
        raise RuntimeError(f"Erro ElevenLabs: {res.text[:200]}")

    with open(caminho_saida, "wb") as f:
        f.write(res.content)
    log(f"Áudio gerado: {Path(caminho_saida).stat().st_size/1024:.0f} KB")
    return True


def gerar_audio_gtts(roteiro: str, caminho_saida: Path) -> bool:
    """Voz gratuita — sem necessidade de API key"""
    if not gTTS:
        raise RuntimeError("gtts não instalado → pip install gtts")
    log("Gerando voz com gTTS (gratuito)...", "PROC")
    tts = gTTS(text=roteiro, lang="pt", slow=False)
    tts.save(str(caminho_saida))
    log(f"Áudio gerado: {Path(caminho_saida).stat().st_size/1024:.0f} KB")
    return True


async def _edge_tts_async(texto: str, caminho_saida: Path) -> None:
    communicate = edge_tts.Communicate(texto, voice="pt-BR-AntonioNeural", rate="+5%")

    await communicate.save(str(caminho_saida))


def gerar_audio_edge(roteiro: str, caminho_saida: Path) -> bool:
    """Voz gratuita usando Edge TTS"""

    log("Gerando voz com Edge TTS...", "PROC")

    asyncio.run(_edge_tts_async(roteiro, caminho_saida))

    log(f"Áudio gerado: {Path(caminho_saida).stat().st_size/1024:.0f} KB")

    return True


def gerar_audio(roteiro: str, caminho_saida: Path) -> bool:
    """
    Prioridade:

    1 - ElevenLabs
    2 - Edge TTS
    3 - gTTS
    """

    if CHAVE_ELEVENLABS:

        try:
            log("Tentando ElevenLabs...", "PROC")
            return gerar_audio_elevenlabs(roteiro, caminho_saida)

        except Exception as e:
            log(f"ElevenLabs indisponível ({e})", "AVISO")

    try:
        log("Alternando para Edge TTS...", "PROC")
        return gerar_audio_edge(roteiro, caminho_saida)

    except Exception as e:
        log(f"Edge TTS falhou ({e})", "AVISO")

    log("Alternando para gTTS...", "PROC")

    return gerar_audio_gtts(roteiro, caminho_saida)


def obter_duracao_audio(caminho: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(caminho),
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=cfg.timeout_ffprobe,
    )
    try:
        return float(json.loads(res.stdout)["format"]["duration"])
    except Exception:
        return 0.0


# ─── ETAPA 3: GERAR LEGENDA ASS ──────────────────────────


def roteiro_para_ass(
    roteiro: str,
    duracao_audio: float,
    caminho_saida: Path,
    modo: str = "frase",
) -> None:
    """Gera ASS sincronizada por frase ou por grupos de palavras.

    ``modo='palavras'`` é opt-in: não exige Whisper e mantém o fallback por frase.
    """
    cor = CORES_ASS.get(COR_LEGENDA, "&H00FFFFFF")
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
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sc = s % 60
        return f"{h}:{m:02d}:{sc:05.2f}"

    # Frases são o modo conservador; grupos de 3-5 palavras aumentam o ritmo visual.
    frases = re.split(r"(?<=[.!?,;])\s+", roteiro.strip())
    frases = [f.strip() for f in frases if f.strip()]
    if modo == "palavras":
        frases = [
            " ".join(palavras[i : i + 4])
            for frase in frases
            for palavras in [frase.split()]
            for i in range(0, len(palavras), 4)
        ]
    elif modo != "frase":
        raise ValueError("modo deve ser 'frase' ou 'palavras'")

    palavras_total = sum(len(f.split()) for f in frases)
    seg_por_palavra = duracao_audio / max(palavras_total, 1)

    linhas = [header]
    t_atual = 0.2  # pequeno delay inicial

    for frase in frases:
        palavras_frase = len(frase.split())
        duracao_frase = palavras_frase * seg_por_palavra

        # Quebrar frases longas em 2 linhas
        if len(frase) > 45:
            meio = len(frase) // 2
            esp = frase.rfind(" ", 0, meio)
            if esp > 0:
                frase = frase[:esp] + r"\N" + frase[esp + 1 :]

        t_fim = min(t_atual + duracao_frase, duracao_audio - 0.1)
        linhas.append(
            f"Dialogue: 0,{t2ass(t_atual)},{t2ass(t_fim)},Default,,0,0,0,,{frase}"
        )
        t_atual = t_fim + 0.05

    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


# ─── ETAPA 4: MONTAR VÍDEO ───────────────────────────────


def obter_fundo_aleatorio() -> Optional[Path]:
    """Retorna um vídeo de fundo aleatório da pasta fundos/ ou subpastas."""
    pasta = Path(PASTA_FUNDOS)
    if pasta.exists():
        # Buscar na raiz E em subpastas (fundos/ceu/, fundos/natureza/, etc.)
        videos = (
            list(pasta.glob("*.mp4"))
            + list(pasta.glob("*.mov"))
            + list(pasta.glob("**/*.mp4"))
            + list(pasta.glob("**/*.mov"))
        )
        # Remover duplicatas mantendo ordem aleatória
        videos = list(dict.fromkeys(videos))
        if videos:
            return random.choice(videos)

    # Sem fundo disponível — gera fundo preto
    return None


def obter_musica_aleatoria() -> Optional[Path]:
    """Retorna uma música instrumental aleatória"""
    pasta = Path(PASTA_MUSICAS)
    if pasta.exists():
        musicas = (
            list(pasta.glob("*.mp3"))
            + list(pasta.glob("*.wav"))
            + list(pasta.glob("*.m4a"))
        )
        if musicas:
            return random.choice(musicas)
    return None


def montar_video(dados_roteiro: dict, caminho_audio: Path, pasta_saida: Path) -> tuple:
    """Monta o vídeo final com fundo + áudio + legenda + logo"""
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    duracao = obter_duracao_audio(caminho_audio)
    if duracao < 1:
        log("Áudio inválido ou muito curto.", "ERRO")
        return None, None

    log(f"Duração do áudio: {duracao:.1f}s", "PROC")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    fmt = dados_roteiro.get("formato", "video")
    nome_base = f"{fmt}_{ts}"
    saida_mp4 = pasta_saida / f"{nome_base}.mp4"
    saida_txt = pasta_saida / f"{nome_base}.txt"

    fundo = obter_fundo_aleatorio()
    musica = obter_musica_aleatoria() if dados_roteiro.get("usar_musica", getattr(cfg, "usar_musica_padrao", False)) else None
    modo_legenda = dados_roteiro.get("modo_legenda", getattr(cfg, "modo_legenda", "frase"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ass_path = tmp / "legenda.ass"
        roteiro_para_ass(
            dados_roteiro["roteiro"], duracao, ass_path, modo=modo_legenda
        )

        ass_esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
        nome_esc = NOME_CANAL.replace("@", "\\@")

        # ── Montar inputs ────────────────────────────────
        inputs = []

        if fundo:
            # Loop do vídeo de fundo se for mais curto que o áudio
            inputs += ["-stream_loop", "-1", "-i", str(fundo)]
            log(f"Fundo: {fundo.name}", "PROC")
        else:
            # Fundo preto gerado
            inputs += ["-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30"]
            log("Fundo: preto (coloque vídeos em fundos/)", "AVISO")

        inputs += ["-i", str(caminho_audio)]

        if musica:
            inputs += ["-stream_loop", "-1", "-i", str(musica)]
            log(f"Música: {musica.name}", "PROC")

        # ── Filtros de vídeo ─────────────────────────────
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"ass='{ass_esc}',"
            f"drawtext=text='{nome_esc}':fontcolor=white:fontsize=26:"
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
            ["ffmpeg", "-y"]
            + inputs
            + ["-t", str(duracao + 0.5)]  # duração exata do áudio + buffer
            + ["-vf", vf]
            + ["-filter_complex", af]
            + ["-map", "0:v", "-map", map_audio]
            + [
                "-c:v",
                "libx264",
                "-crf",
                str(QUALIDADE_CRF),
                "-preset",
                VELOCIDADE_ENC,
                "-profile:v",
                "high",
                "-level",
                "4.1",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-map_metadata",
                "-1",
                "-metadata",
                "title=",
                "-metadata",
                "comment=",
                "-metadata",
                "encoder=",
                str(saida_mp4),
            ]
        )

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=cfg.timeout_ffmpeg_encode,
        )

        if res.returncode != 0:
            log(f"Erro FFmpeg: {res.stderr[-300:]}", "ERRO")
            return None, None

        tam = saida_mp4.stat().st_size / (1024 * 1024)
        dur_final = obter_duracao_audio(saida_mp4)
        log(f"✅ Vídeo pronto: {saida_mp4.name} ({tam:.1f}MB | {dur_final:.1f}s)")

    # ── Salvar .txt com título/descrição/hashtags ────────
    hashtags_str = " ".join(dados_roteiro.get("hashtags", []))
    conteudo_txt = (
        f"=== YOUTUBE SHORTS ===\n"
        f"TÍTULO:\n{dados_roteiro.get('titulo_yt','')}\n\n"
        f"DESCRIÇÃO:\n{dados_roteiro.get('descricao','')}\n\n"
        f"HASHTAGS:\n{hashtags_str}\n\n"
        f"=== TIKTOK ===\n"
        f"TÍTULO:\n{dados_roteiro.get('titulo_tiktok','')}\n\n"
        f"DESCRIÇÃO:\n{dados_roteiro.get('descricao','')}\n\n"
        f"HASHTAGS:\n{hashtags_str}\n\n"
        f"=== ENGAJAMENTO ===\n"
        f"SÉRIE: {dados_roteiro.get('serie','')} #{dados_roteiro.get('numero_serie','')}\n"
        f"GANCHO: {dados_roteiro.get('gancho','')}\n"
        f"CTA NO VÍDEO: {dados_roteiro.get('cta_video','')}\n"
        f"PERGUNTA PARA COMENTÁRIOS: {dados_roteiro.get('cta_comentario','')}\n"
        f"TRANSPARÊNCIA: {'Roteiro assistido por IA e revisado editorialmente.' if dados_roteiro.get('transparencia_ia') else ''}\n\n"
        f"=== INFO ===\n"
        f"FORMATO: {dados_roteiro.get('formato','')}\n"
        f"DURAÇÃO: {dur_final:.1f}s\n"
        f"TEMA: {dados_roteiro.get('tema') or dados_roteiro.get('versiculo','')}\n"
    )
    saida_txt.write_text(conteudo_txt, encoding="utf-8")
    log(f"📝 {saida_txt.name}")

    return saida_mp4, saida_txt


# ─── PIPELINE POR FORMATO ────────────────────────────────


def gerar_video(
    formato: str,
    tema: Optional[str] = None,
    duracao: Optional[tuple] = None,
    usar_musica: Optional[bool] = None,
    modo_legenda: Optional[str] = None,
) -> tuple:
    """Pipeline completo para um único vídeo"""

    banco.inicializar()

    Path(PASTA_AUDIO_TEMP).mkdir(exist_ok=True)
    Path(PASTA_PRONTOS).mkdir(exist_ok=True)

    log(f"Gerando vídeo: {formato.upper()}", "PROC")
    print("─" * 50)

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

    if usar_musica is not None:
        dados["usar_musica"] = usar_musica
    if modo_legenda is not None:
        dados["modo_legenda"] = modo_legenda

    custo_total += dados.get("custo_usd", 0)
    palavras = len(dados["roteiro"].split())
    log(f"Roteiro: {palavras} palavras | custo: ${dados['custo_usd']:.4f}")

    # 2. Gerar áudio com cleanup garantido
    ts = datetime.now().strftime("%H%M%S")
    audio_path = Path(PASTA_AUDIO_TEMP) / f"audio_{formato}_{ts}.mp3"

    try:
        ok = gerar_audio(dados["roteiro"], audio_path)
        if not ok:
            log("Falha ao gerar áudio.", "ERRO")
            return None, None

        # 3. Montar vídeo
        video_out, txt_out = montar_video(dados, audio_path, PASTA_PRONTOS)

        if video_out:
            vid_id = banco.registrar_video(
                url=f"gerado_{formato}_{ts}",
                titulo=dados.get("titulo_yt", ""),
                duracao_s=obter_duracao_audio(video_out),
                caminho_arquivo=str(video_out),
            )
            banco.registrar_corte(
                video_id=vid_id,
                numero=1,
                corte_info={
                    "categoria": "ia",
                    "tipo": formato,
                    "titulo": dados.get("titulo_yt", ""),
                    "gancho": dados["roteiro"].split(".")[0][:80],
                    "inicio": 0,
                    "fim": obter_duracao_audio(video_out),
                },
                caminho_video=video_out,
                caminho_txt=txt_out,
                desc_info=dados,
            )
            log("Registrado no banco", "DB")

        return video_out, txt_out

    finally:
        # Limpar áudio temp - SEMPRE executado, mesmo se houver erro
        if audio_path.exists():
            try:
                audio_path.unlink()
            except Exception as e:
                logger.warning(
                    "Falha ao limpar arquivo temporário %s: %s", audio_path, e
                )

# ─── PIPELINE DO DIA ─────────────────────────────────────


def gerar_videos_do_dia(
    formatos: Optional[list] = None, quantidade: Optional[int] = None
) -> list:
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

    print("\n" + "═" * 58)
    print("  GERADOR DE CONTEÚDO RELIGIOSO")
    print(f"  {len(formatos_usar)} vídeo(s) para gerar hoje")
    print("═" * 58 + "\n")

    # Mostrar distribuição de duração
    duracoes = {
        "reflexao": f"{DURACAO_REFLEXAO[0]}–{DURACAO_REFLEXAO[1]}s",
        "historia": f"{DURACAO_HISTORIA[0]}–{DURACAO_HISTORIA[1]}s",
        "versiculo": f"{DURACAO_VERSICULO[0]}–{DURACAO_VERSICULO[1]}s",
    }
    longos = sum(1 for f in formatos_usar if f in ["reflexao", "historia"])
    medios = sum(1 for f in formatos_usar if f == "versiculo")
    print(f"  Distribuição: {longos} longo(s) >60s | {medios} médio(s) =60s")
    print(f"  Pasta de saída: {Path(PASTA_PRONTOS).resolve()}\n")

    prontos = []
    custo_total = 0.0

    for i, fmt in enumerate(formatos_usar, 1):
        print(f"\n[{i}/{len(formatos_usar)}] {fmt.upper()} ({duracoes.get(fmt,'?')})")
        video, txt = gerar_video(fmt)
        if video:
            prontos.append((video, txt, fmt))

    print("\n" + "═" * 58)
    print(f"  ✅ {len(prontos)}/{len(formatos_usar)} vídeos gerados")
    print(f"  📁 {Path(PASTA_PRONTOS).resolve()}")
    print("═" * 58 + "\n")

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
    custo_total_local = sum(d.get("custo_usd", 0) for d in [{}])  # placeholder
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
    parser.add_argument(
        "--formato",
        choices=["reflexao", "historia", "versiculo"],
        help="Gerar apenas um formato específico",
    )
    parser.add_argument("--tema", help="Tema ou versículo específico")
    parser.add_argument(
        "--quantidade", type=int, help="Quantidade total de vídeos a gerar"
    )
    parser.add_argument(
        "--plataforma",
        choices=["youtube", "tiktok"],
        help="Perfil opcional de duração da plataforma",
    )
    parser.add_argument(
        "--musica", action="store_true", help="Ativa música local licenciada"
    )
    parser.add_argument(
        "--legendas-palavras",
        action="store_true",
        help="Usa legendas em grupos de palavras",
    )
    parser.add_argument(
        "--longo",
        action="store_true",
        help="Gerar apenas vídeos longos (reflexão + história)",
    )
    args = parser.parse_args()

    if args.longo:
        gerar_videos_do_dia(formatos=["reflexao", "historia", "reflexao"])
    elif args.formato:
        verificar_deps()
        duracao = None
        if args.plataforma == "youtube":
            duracao = cfg.duracao_youtube
        elif args.plataforma == "tiktok":
            duracao = cfg.duracao_tiktok
        video, txt = gerar_video(
            args.formato,
            tema=args.tema,
            duracao=duracao,
            usar_musica=args.musica,
            modo_legenda="palavras" if args.legendas_palavras else "frase",
        )
        # As flags também podem ser aplicadas diretamente por configuração; o
        # CLI mantém compatibilidade e deixa o pipeline principal inalterado.
        if video and txt:
            log(f"Perfil {args.plataforma or 'padrão'} concluído", "PROC")
    else:
        formatos = None
        if args.quantidade:
            # Mais longos quando quantidade é maior
            base = ["reflexao", "historia", "versiculo"]
            formatos = None  # usa distribuição padrão
        gerar_videos_do_dia(quantidade=args.quantidade)


if __name__ == "__main__":
    main()
