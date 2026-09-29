#!/usr/bin/env python3
"""
Funções utilitárias compartilhadas por todos os scripts.
Elimina código duplicado entre youtube_para_shorts.py,
processar_video.py e gerador_conteudo.py.
"""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── LOGGING ─────────────────────────────────────────────

NIVEL_ICONS = {
    "INFO": "✓",
    "ERRO": "✗",
    "AVISO": "⚠",
    "PROC": "→",
    "IA": "🤖",
    "DB": "🗄️",
    "YT": "📺",
}


def log(msg: str, nivel: str = "INFO") -> None:
    hora = datetime.now().strftime("%H:%M:%S")
    icone = NIVEL_ICONS.get(nivel, "·")
    print(f"[{hora}] {icone} {msg}")


# ─── FFPROBE ─────────────────────────────────────────────


def obter_duracao(caminho: Path) -> float:
    """Retorna duração em segundos via ffprobe. Retorna 0.0 em falha."""
    try:
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
            timeout=30,
        )
        if res.returncode == 0:
            return float(json.loads(res.stdout)["format"]["duration"])
    except Exception as e:
        logger.warning("Falha ao obter duração de %s: %s", caminho, e)
    return 0.0


def obter_info_video(caminho: Path) -> dict:
    """Retorna dict com largura, altura, fps, duracao, tem_audio."""
    info = {"duracao": 0.0, "largura": 0, "altura": 0, "fps": 30.0, "tem_audio": False}
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(caminho),
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        dados = json.loads(res.stdout)
        for s in dados.get("streams", []):
            if s.get("codec_type") == "video":
                info["largura"] = int(s.get("width", 0))
                info["altura"] = int(s.get("height", 0))
                fps_str = s.get("r_frame_rate", "30/1")
                try:
                    n, d = fps_str.split("/")
                    info["fps"] = round(int(n) / int(d), 2)
                except Exception:
                    # fps_str em formato inesperado (ex: não é "N/D"): mantém
                    # o default 30.0 já setado em info["fps"] antes do bloco.
                    # Degradação para chute razoável, não perda de dado.
                    pass
            elif s.get("codec_type") == "audio":
                info["tem_audio"] = True
        info["duracao"] = float(dados.get("format", {}).get("duration", 0))
    except Exception as e:
        logger.warning("Falha ao inspecionar vídeo %s: %s", caminho, e)
    return info


# ─── LEGENDA ASS ─────────────────────────────────────────

CORES_ASS = {
    "white": "&H00FFFFFF",
    "yellow": "&H0000FFFF",
    "cyan": "&H00FFFF00",
}


def t2ass(s: float) -> str:
    """Converte segundos float para formato de tempo ASS (H:MM:SS.cc)."""
    s = max(0.0, s)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sc = s % 60
    return f"{h}:{m:02d}:{sc:05.2f}"


def gerar_ass_de_segmentos(
    segmentos: list,
    inicio_corte: float,
    fim_corte: float,
    caminho_saida: Path,
    cor: str = "white",
    tamanho_font: int = 20,
) -> None:
    """
    Gera arquivo ASS com legendas para um intervalo do vídeo.
    Reutilizado por youtube_para_shorts.py e processar_video.py.
    """
    cor_ass = CORES_ASS.get(cor, "&H00FFFFFF")
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{tamanho_font},{cor_ass},&H000000FF,"
        "&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,100,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    linhas = [header]
    for seg in segmentos:
        if seg["end"] <= inicio_corte or seg["start"] >= fim_corte:
            continue
        t_ini = max(0.0, seg["start"] - inicio_corte)
        t_fim = min(fim_corte - inicio_corte, seg["end"] - inicio_corte)
        texto = seg["text"].strip().replace("\n", " ")
        # Quebrar linhas longas em 2
        if len(texto) > 38:
            meio = len(texto) // 2
            esp = texto.rfind(" ", 0, meio)
            if esp > 0:
                texto = texto[:esp] + r"\N" + texto[esp + 1 :]
        linhas.append(
            f"Dialogue: 0,{t2ass(t_ini)},{t2ass(t_fim)},Default,,0,0,0,,{texto}"
        )
    caminho_saida.write_text("\n".join(linhas), encoding="utf-8")


def gerar_ass_de_roteiro(
    roteiro: str,
    duracao_audio: float,
    caminho_saida: Path,
    cor: str = "white",
    tamanho_font: int = 22,
) -> None:
    """
    Gera ASS estimando timestamps por frase (para vídeos gerados).
    Usado pelo gerador_conteudo.py.
    """
    cor_ass = CORES_ASS.get(cor, "&H00FFFFFF")
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{tamanho_font},{cor_ass},&H000000FF,"
        "&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,100,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    frases = [
        f.strip() for f in re.split(r"(?<=[.!?,;])\s+", roteiro.strip()) if f.strip()
    ]
    palavras_total = sum(len(f.split()) for f in frases) or 1
    seg_por_palavra = duracao_audio / palavras_total

    linhas = [header]
    t_atual = 0.2
    for frase in frases:
        dur = len(frase.split()) * seg_por_palavra
        if len(frase) > 45:
            meio = len(frase) // 2
            esp = frase.rfind(" ", 0, meio)
            if esp > 0:
                frase = frase[:esp] + r"\N" + frase[esp + 1 :]
        t_fim = min(t_atual + dur, duracao_audio - 0.1)
        linhas.append(
            f"Dialogue: 0,{t2ass(t_atual)},{t2ass(t_fim)},Default,,0,0,0,,{frase}"
        )
        t_atual = t_fim + 0.05
    caminho_saida.write_text("\n".join(linhas), encoding="utf-8")


# ─── NOME DE ARQUIVO SEGURO ──────────────────────────────


def nome_seguro(texto: str, max_len: int = 35) -> str:
    """Remove caracteres inválidos para nome de arquivo."""
    if not texto:
        return ""
    s = re.sub(r"[^\w\s.-]", "", texto)  # permite letras, números, _, espaço, ., -
    s = re.sub(r"\s+", "_", s.strip())
    return s[:max_len]


# ─── PARSER JSON ROBUSTO ─────────────────────────────────


def parse_json_robusto(texto: str) -> Any:
    """
    Tenta parsear JSON retornado pela IA.
    Remove markdown fences e tenta extrair array/objeto se necessário.
    """
    texto = re.sub(r"```json|```", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        # Tentar extrair o primeiro array ou objeto JSON do texto
        for padrao in (r"\[.*\]", r"\{.*\}"):
            match = re.search(padrao, texto, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue
        raise ValueError(
            f"Não foi possível parsear JSON da resposta da IA:\n{texto[:300]}"
        )


# ─── CUSTO API ───────────────────────────────────────────


def calcular_custo_claude(usage: Any) -> float:
    """Calcula custo aproximado em USD para Claude Sonnet."""
    # $3/M tokens input, $15/M tokens output
    return (usage.input_tokens * 3 + usage.output_tokens * 15) / 1_000_000


# ─── SALVAR TXT DE PUBLICAÇÃO ────────────────────────────


def salvar_txt_publicacao(
    caminho: Path, dados: dict, corte_info: dict | None = None
) -> None:
    """Salva arquivo .txt com título, descrição e hashtags para publicação."""
    hashtags_str = " ".join(dados.get("hashtags", []))
    titulo_yt = dados.get(
        "titulo_yt", corte_info.get("titulo", "") if corte_info else ""
    )
    titulo_tt = dados.get("titulo_tiktok", titulo_yt)
    descricao = dados.get("descricao", "")
    gancho = (
        corte_info.get("gancho", "") if corte_info else dados.get("roteiro", "")[:80]
    )
    tipo = (
        corte_info.get("tipo", dados.get("formato", ""))
        if corte_info
        else dados.get("formato", "")
    )
    dur = corte_info.get("duracao", 0) if corte_info else 0
    serie = dados.get("serie", tipo.upper())
    numero_serie = dados.get("numero_serie", "")
    cta_video = dados.get("cta_video", "")
    cta_comentario = dados.get("cta_comentario", "")

    conteudo = (
        f"=== YOUTUBE SHORTS ===\n"
        f"TÍTULO:\n{titulo_yt}\n\n"
        f"DESCRIÇÃO:\n{descricao}\n\n"
        f"HASHTAGS:\n{hashtags_str}\n\n"
        f"=== TIKTOK ===\n"
        f"TÍTULO:\n{titulo_tt}\n\n"
        f"DESCRIÇÃO:\n{descricao}\n\n"
        f"HASHTAGS:\n{hashtags_str}\n\n"
        f"=== INFO ===\n"
        f"TIPO: {tipo}\n"
        f"DURAÇÃO: {dur:.0f}s\n"
        f"SÉRIE: {serie} #{numero_serie}\n"
        f"GANCHO: {gancho}\n"
        f"CTA NO VÍDEO: {cta_video}\n"
        f"PERGUNTA PARA COMENTÁRIOS: {cta_comentario}\n"
    )
    caminho.write_text(conteudo, encoding="utf-8")


def gerar_thumbnail(
    caminho_video: str | Path,
    caminho_saida: str | Path,
    texto_titulo: str = "",
) -> Path | None:
    """Extrai um frame do vídeo como thumbnail, sem exigir dependências novas."""
    video = Path(caminho_video)
    saida = Path(caminho_saida).with_suffix(".jpg")
    if not video.exists():
        return None
    cmd = [
        "ffmpeg", "-y", "-ss", "00:00:03", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(saida),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        logger.warning("Não foi possível gerar thumbnail para %s", video)
        return None
    if not saida.exists() or saida.stat().st_size == 0:
        return None
    return saida
