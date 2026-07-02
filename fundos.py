#!/usr/bin/env python3
"""
=======================================================
  DOWNLOAD AUTOMÁTICO DE FUNDOS E MÚSICAS
=======================================================
  Baixa vídeos de fundo e músicas instrumentais
  gratuitos e sem copyright para usar nos vídeos gerados.

  FONTES:
  • Pexels  — vídeos de natureza, céu, luz, água
  • Pixabay — músicas instrumentais cristãs/gospel

  CONFIGURAÇÃO (gratuita):
  1. Crie conta em pexels.com/api → copie a API key
  2. Crie conta em pixabay.com/api → copie a API key
  3. Adicione no .env:
       PEXELS_API_KEY=sua_chave
       PIXABAY_API_KEY=sua_chave

  USO:
    python fundos.py                    (baixa tudo)
    python fundos.py --videos           (só vídeos de fundo)
    python fundos.py --musicas          (só músicas)
    python fundos.py --tema ceu         (vídeos de um tema)
    python fundos.py --status           (mostra o que já tem)
    python fundos.py --minimo           (garante mínimo por tema)
=======================================================
"""

import json
import logging
import os
import sys
import time
import argparse
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# ── Carregar .env ──────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# ── Configurações ──────────────────────────────────────
PEXELS_API_KEY  = os.getenv("PEXELS_API_KEY",  "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

PASTA_FUNDOS  = Path("fundos")
PASTA_MUSICAS = Path("musicas")
PASTA_CACHE   = Path(".cache_fundos")   # evita baixar o mesmo arquivo 2x

# Mínimo de arquivos por categoria (garante variedade)
MIN_VIDEOS_POR_TEMA = 3
MIN_MUSICAS_TOTAL   = 8

# Qualidade de vídeo alvo (pixels de altura)
QUALIDADE_VIDEO = 1080   # Full HD é suficiente — 4K seria grande demais

# Tempo máximo de vídeo de fundo (segundos)
DURACAO_MAX_FUNDO = 120

# ── Temas de vídeo por formato de conteúdo ────────────
TEMAS_FUNDO = {
    "ceu": {
        "queries_pexels":  ["sky clouds sunrise", "heaven light clouds", "blue sky peaceful"],
        "queries_pixabay": ["sky clouds peaceful", "sunrise sky"],
        "formatos":        ["reflexao", "versiculo"],
    },
    "natureza": {
        "queries_pexels":  ["nature peaceful forest", "green nature calm", "waterfall nature"],
        "queries_pixabay": ["nature forest peaceful", "green landscape calm"],
        "formatos":        ["reflexao", "historia"],
    },
    "luz": {
        "queries_pexels":  ["sunlight rays bokeh", "golden light particles", "light beams divine"],
        "queries_pixabay": ["sunlight golden bokeh", "light rays peaceful"],
        "formatos":        ["reflexao", "versiculo", "historia"],
    },
    "agua": {
        "queries_pexels":  ["calm water waves", "ocean waves peaceful", "river flowing calm"],
        "queries_pixabay": ["calm water ripple", "ocean peaceful"],
        "formatos":        ["reflexao"],
    },
    "montanha": {
        "queries_pexels":  ["mountain landscape majestic", "mountain sunrise mist"],
        "queries_pixabay": ["mountain landscape peaceful"],
        "formatos":        ["historia"],
    },
    "cidade_noite": {
        "queries_pexels":  ["city night lights bokeh", "night sky stars"],
        "queries_pixabay": ["night city bokeh peaceful"],
        "formatos":        ["reflexao"],
    },
}

# ── Queries para músicas ────────────────────────────────
QUERIES_MUSICA = [
    "gospel instrumental",
    "christian worship instrumental",
    "peaceful piano spiritual",
    "ambient worship music",
    "christian meditation music",
    "gospel piano background",
    "spiritual ambient peaceful",
    "church organ instrumental",
]

EXTENSOES_VIDEO  = {".mp4", ".mov", ".webm"}
EXTENSOES_MUSICA = {".mp3", ".wav", ".ogg", ".m4a"}


def log(msg: str, nivel: str = "INFO") -> None:
    hora  = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO":"✓","ERRO":"✗","AVISO":"⚠","PROC":"→","DL":"⬇"}
    print(f"[{hora}] {icons.get(nivel,'·')} {msg}")
    if nivel == "ERRO":    logger.error(msg)
    elif nivel == "AVISO": logger.warning(msg)
    else:                  logger.info(msg)


def _hash_url(url: str) -> str:
    """Gera hash curto de uma URL para controle de cache.

    Uso não criptográfico: apenas chave de deduplicação de download
    (identificar se uma URL já foi baixada). usedforsecurity=False
    documenta a intenção e evita falso positivo de scanner de segurança.
    """
    return hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:12]


def _ja_baixado(url: str) -> bool:
    """Verifica se a URL já foi baixada anteriormente."""
    PASTA_CACHE.mkdir(exist_ok=True)
    return (PASTA_CACHE / _hash_url(url)).exists()


def _marcar_baixado(url: str) -> None:
    """Marca URL como baixada no cache."""
    PASTA_CACHE.mkdir(exist_ok=True)
    (PASTA_CACHE / _hash_url(url)).write_text(url)


def _baixar_arquivo(url: str, destino: Path,
                    nome_exibicao: str = "") -> bool:
    """
    Baixa um arquivo com barra de progresso simples.
    Retorna True se bem-sucedido.
    """
    if _ja_baixado(url):
        log(f"Cache: {destino.name} já baixado anteriormente")
        return True

    try:
        resp = requests.get(url, stream=True, timeout=60,
                            headers={"User-Agent": "BoomVibes/1.0"})
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        baixado = 0
        destino.parent.mkdir(parents=True, exist_ok=True)

        with open(destino, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):  # 256KB chunks
                f.write(chunk)
                baixado += len(chunk)
                if total:
                    pct = baixado / total * 100
                    print(f"\r  ⬇ {nome_exibicao} {pct:.0f}%", end="", flush=True)

        print()  # nova linha após progresso
        _marcar_baixado(url)
        tamanho = destino.stat().st_size / (1024 * 1024)
        log(f"Salvo: {destino.name} ({tamanho:.1f}MB)", "DL")
        return True

    except requests.exceptions.Timeout:
        log(f"Timeout ao baixar: {nome_exibicao}", "AVISO")
        if destino.exists(): destino.unlink()
        return False
    except Exception as e:
        log(f"Erro ao baixar {nome_exibicao}: {e}", "ERRO")
        if destino.exists(): destino.unlink()
        return False


# ── PEXELS — Vídeos ────────────────────────────────────

def _buscar_pexels(query: str, por_pagina: int = 10) -> list[dict]:
    """Busca vídeos no Pexels API."""
    if not PEXELS_API_KEY:
        return []

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={
                "query":    query,
                "per_page": por_pagina,
                "size":     "medium",   # small | medium | large
            },
            timeout=15
        )
        resp.raise_for_status()
        return resp.json().get("videos", [])
    except Exception as e:
        log(f"Pexels API erro ({query}): {e}", "AVISO")
        return []


def _melhor_arquivo_pexels(video: dict) -> Optional[dict]:
    """
    Escolhe o melhor arquivo de vídeo do resultado Pexels.
    Preferência: Full HD (1080p), não 4K (muito pesado).
    """
    arquivos = video.get("video_files", [])
    if not arquivos:
        return None

    # Ordenar por qualidade — preferir 1080p
    def prioridade(f):
        h = f.get("height", 0)
        if h == QUALIDADE_VIDEO:
            return 0   # perfeito
        elif h > QUALIDADE_VIDEO:
            return 2   # 4K — aceita mas não é ideal
        else:
            return 1   # abaixo de 1080p

    arquivos_mp4 = [f for f in arquivos if f.get("file_type") == "video/mp4"]
    if not arquivos_mp4:
        arquivos_mp4 = arquivos

    return min(arquivos_mp4, key=prioridade)


def baixar_videos_pexels(tema: str, queries: list[str],
                          quantidade: int = MIN_VIDEOS_POR_TEMA) -> int:
    """
    Baixa vídeos de fundo do Pexels para um tema.
    Retorna número de vídeos baixados.
    """
    PASTA_FUNDOS.mkdir(exist_ok=True)
    pasta_tema = PASTA_FUNDOS / tema
    pasta_tema.mkdir(exist_ok=True)

    # Contar quantos já existem
    ja_tem = len(list(pasta_tema.glob("*.mp4")))
    if ja_tem >= quantidade:
        log(f"Fundos/{tema}: já tem {ja_tem} vídeos — pulando")
        return 0

    precisa = quantidade - ja_tem
    baixados = 0

    for query in queries:
        if baixados >= precisa:
            break

        log(f"Buscando no Pexels: '{query}'...", "PROC")
        videos = _buscar_pexels(query, por_pagina=8)

        for video in videos:
            if baixados >= precisa:
                break

            # Filtrar por duração
            duracao = video.get("duration", 0)
            if duracao > DURACAO_MAX_FUNDO:
                continue

            arquivo = _melhor_arquivo_pexels(video)
            if not arquivo or not arquivo.get("link"):
                continue

            vid_id = video.get("id", baixados)
            nome   = f"{tema}_{vid_id}.mp4"
            dest   = pasta_tema / nome

            if dest.exists():
                continue

            if _baixar_arquivo(arquivo["link"], dest, nome):
                baixados += 1

            time.sleep(0.5)  # respeitar rate limit da API

    log(f"Pexels/{tema}: {baixados} novos vídeos baixados")
    return baixados


# ── PIXABAY — Músicas ──────────────────────────────────

def _buscar_pixabay_musica(query: str, por_pagina: int = 10) -> list[dict]:
    """Busca músicas no Pixabay API."""
    if not PIXABAY_API_KEY:
        return []

    try:
        resp = requests.get(
            "https://pixabay.com/api/music/",
            params={
                "key":      PIXABAY_API_KEY,
                "q":        query,
                "per_page": por_pagina,
                "category": "ambient",
            },
            timeout=15
        )
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception as e:
        log(f"Pixabay API erro ({query}): {e}", "AVISO")
        return []


def baixar_musicas_pixabay(quantidade: int = MIN_MUSICAS_TOTAL) -> int:
    """
    Baixa músicas instrumentais do Pixabay.
    Retorna número de músicas baixadas.
    """
    PASTA_MUSICAS.mkdir(exist_ok=True)

    ja_tem = len(list(PASTA_MUSICAS.glob("*.mp3")))
    if ja_tem >= quantidade:
        log(f"Músicas: já tem {ja_tem} — pulando")
        return 0

    precisa  = quantidade - ja_tem
    baixados = 0

    for query in QUERIES_MUSICA:
        if baixados >= precisa:
            break

        log(f"Buscando no Pixabay: '{query}'...", "PROC")
        musicas = _buscar_pixabay_musica(query)

        for musica in musicas:
            if baixados >= precisa:
                break

            url = musica.get("audio", "")
            if not url:
                continue

            nome = f"instrumental_{musica.get('id', baixados)}.mp3"
            dest = PASTA_MUSICAS / nome

            if dest.exists():
                continue

            titulo = musica.get("title", nome)
            if _baixar_arquivo(url, dest, titulo):
                baixados += 1

            time.sleep(0.3)

    log(f"Pixabay: {baixados} novas músicas baixadas")
    return baixados


# ── FALLBACK — URLs embutidas (sem API key) ────────────
# Vídeos e músicas com licença Creative Commons 0 (CC0)
# Serve como fallback se o usuário não configurar as APIs

FUNDOS_CC0 = {
    "ceu": [
        "https://videos.pexels.com/video-files/856882/856882-hd_1920_1080_25fps.mp4",
        "https://videos.pexels.com/video-files/3571264/3571264-hd_1920_1080_30fps.mp4",
    ],
    "natureza": [
        "https://videos.pexels.com/video-files/1448735/1448735-hd_1920_1080_25fps.mp4",
        "https://videos.pexels.com/video-files/3571264/3571264-hd_1920_1080_30fps.mp4",
    ],
    "luz": [
        "https://videos.pexels.com/video-files/3571264/3571264-hd_1920_1080_30fps.mp4",
        "https://videos.pexels.com/video-files/856882/856882-hd_1920_1080_25fps.mp4",
    ],
}

MUSICAS_CC0 = [
    "https://cdn.pixabay.com/download/audio/2022/01/18/audio_d0c6ff2c02.mp3",
    "https://cdn.pixabay.com/download/audio/2021/11/25/audio_5f5e4bbfb0.mp3",
    "https://cdn.pixabay.com/download/audio/2022/03/10/audio_270f49fcdf.mp3",
]


def baixar_fallback() -> dict:
    """
    Baixa assets CC0 embutidos quando APIs não estão configuradas.
    Garante que o sistema funciona mesmo sem API keys do Pexels/Pixabay.
    """
    resultado = {"videos": 0, "musicas": 0}

    log("Usando assets CC0 embutidos (sem API keys)", "AVISO")
    log("Configure PEXELS_API_KEY e PIXABAY_API_KEY no .env para mais variedade")

    for tema, urls in FUNDOS_CC0.items():
        pasta = PASTA_FUNDOS / tema
        pasta.mkdir(parents=True, exist_ok=True)
        for i, url in enumerate(urls):
            dest = pasta / f"{tema}_cc0_{i+1}.mp4"
            if not dest.exists():
                if _baixar_arquivo(url, dest, f"{tema}_cc0_{i+1}"):
                    resultado["videos"] += 1

    PASTA_MUSICAS.mkdir(exist_ok=True)
    for i, url in enumerate(MUSICAS_CC0):
        dest = PASTA_MUSICAS / f"instrumental_cc0_{i+1}.mp3"
        if not dest.exists():
            if _baixar_arquivo(url, dest, f"instrumental_cc0_{i+1}"):
                resultado["musicas"] += 1

    return resultado


# ── PIPELINE PRINCIPAL ─────────────────────────────────

def baixar_tudo(apenas_videos: bool = False,
                apenas_musicas: bool = False,
                tema_especifico: Optional[str] = None) -> dict:
    """Pipeline completo de download de fundos e músicas."""

    resultado = {"videos": 0, "musicas": 0, "erros": 0}

    tem_pexels  = bool(PEXELS_API_KEY)
    tem_pixabay = bool(PIXABAY_API_KEY)

    print("\n" + "═"*55)
    print("  DOWNLOAD DE FUNDOS E MÚSICAS")
    print("═"*55)
    print(f"\n  Pexels  : {'✅ configurado' if tem_pexels  else '⚠️  sem API key'}")
    print(f"  Pixabay : {'✅ configurado' if tem_pixabay else '⚠️  sem API key'}")
    print()

    # Sem nenhuma API — usar fallback CC0
    if not tem_pexels and not tem_pixabay:
        log("Nenhuma API key configurada — baixando assets CC0 embutidos", "AVISO")
        r = baixar_fallback()
        resultado["videos"]  += r["videos"]
        resultado["musicas"] += r["musicas"]
        _imprimir_resumo(resultado)
        return resultado

    # Download de vídeos
    if not apenas_musicas:
        temas = [tema_especifico] if tema_especifico else list(TEMAS_FUNDO.keys())
        print(f"📹 Baixando vídeos de fundo ({len(temas)} tema(s))...\n")

        for tema in temas:
            if tema not in TEMAS_FUNDO:
                log(f"Tema desconhecido: '{tema}'", "AVISO")
                continue

            info = TEMAS_FUNDO[tema]

            if tem_pexels:
                try:
                    n = baixar_videos_pexels(
                        tema=tema,
                        queries=info["queries_pexels"],
                        quantidade=MIN_VIDEOS_POR_TEMA,
                    )
                    resultado["videos"] += n
                except Exception as e:
                    log(f"Erro Pexels/{tema}: {e}", "ERRO")
                    resultado["erros"] += 1
            else:
                # Fallback CC0 para este tema
                if tema in FUNDOS_CC0:
                    pasta = PASTA_FUNDOS / tema
                    pasta.mkdir(parents=True, exist_ok=True)
                    for i, url in enumerate(FUNDOS_CC0[tema]):
                        dest = pasta / f"{tema}_cc0_{i+1}.mp4"
                        if not dest.exists() and _baixar_arquivo(url, dest, f"{tema}_cc0_{i+1}"):
                            resultado["videos"] += 1

    # Download de músicas
    if not apenas_videos:
        print(f"\n🎵 Baixando músicas instrumentais...\n")
        if tem_pixabay:
            try:
                n = baixar_musicas_pixabay(quantidade=MIN_MUSICAS_TOTAL)
                resultado["musicas"] += n
            except Exception as e:
                log(f"Erro Pixabay músicas: {e}", "ERRO")
                resultado["erros"] += 1
        else:
            # Fallback CC0 para músicas
            PASTA_MUSICAS.mkdir(exist_ok=True)
            for i, url in enumerate(MUSICAS_CC0):
                dest = PASTA_MUSICAS / f"instrumental_cc0_{i+1}.mp3"
                if not dest.exists() and _baixar_arquivo(url, dest, f"cc0_{i+1}"):
                    resultado["musicas"] += 1

    _imprimir_resumo(resultado)
    return resultado


def _imprimir_resumo(resultado: dict) -> None:
    print("\n" + "═"*55)
    print(f"  ✅ Vídeos baixados : {resultado['videos']}")
    print(f"  ✅ Músicas baixadas: {resultado['musicas']}")
    if resultado["erros"]:
        print(f"  ⚠️  Erros          : {resultado['erros']}")
    print("═"*55 + "\n")


def mostrar_status() -> None:
    """Mostra o que já tem nas pastas fundos/ e musicas/."""
    print("\n" + "═"*55)
    print("  STATUS DOS ASSETS")
    print("═"*55)

    # Vídeos
    print("\n📹 Vídeos de fundo:\n")
    total_videos = 0
    if PASTA_FUNDOS.exists():
        for tema_dir in sorted(PASTA_FUNDOS.iterdir()):
            if tema_dir.is_dir():
                videos = list(tema_dir.glob("*.mp4")) + list(tema_dir.glob("*.mov"))
                total_videos += len(videos)
                status = "✅" if len(videos) >= MIN_VIDEOS_POR_TEMA else "⚠️ "
                print(f"  {status} fundos/{tema_dir.name:<15} {len(videos)} vídeo(s)")
    else:
        print("  Pasta fundos/ não existe ainda")

    # Músicas
    print("\n🎵 Músicas instrumentais:\n")
    total_musicas = 0
    if PASTA_MUSICAS.exists():
        musicas = (list(PASTA_MUSICAS.glob("*.mp3")) +
                   list(PASTA_MUSICAS.glob("*.wav")) +
                   list(PASTA_MUSICAS.glob("*.m4a")))
        total_musicas = len(musicas)
        status = "✅" if total_musicas >= MIN_MUSICAS_TOTAL else "⚠️ "
        print(f"  {status} musicas/  {total_musicas} arquivo(s)")
    else:
        print("  Pasta musicas/ não existe ainda")

    # Diagnóstico
    print()
    if total_videos < len(TEMAS_FUNDO) * MIN_VIDEOS_POR_TEMA:
        print("  ⚠️  Vídeos insuficientes — rode: python fundos.py --videos")
    if total_musicas < MIN_MUSICAS_TOTAL:
        print("  ⚠️  Músicas insuficientes — rode: python fundos.py --musicas")
    if total_videos >= 3 and total_musicas >= 3:
        print("  ✅ Assets suficientes para produção!")
    print()


def garantir_minimo() -> None:
    """
    Garante o mínimo de assets para o sistema funcionar.
    Chamado automaticamente pelo run_diario.py se necessário.
    """
    videos_ok  = False
    musicas_ok = False

    if PASTA_FUNDOS.exists():
        total = sum(
            len(list(d.glob("*.mp4")))
            for d in PASTA_FUNDOS.iterdir()
            if d.is_dir()
        )
        videos_ok = total >= 3  # mínimo absoluto

    if PASTA_MUSICAS.exists():
        total = len(list(PASTA_MUSICAS.glob("*.mp3")))
        musicas_ok = total >= 3

    if not videos_ok or not musicas_ok:
        logger.info("Assets insuficientes — iniciando download automático")
        baixar_tudo(
            apenas_videos=not musicas_ok and videos_ok,
            apenas_musicas=not videos_ok and musicas_ok,
        )


# ── CLI ────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download automático de fundos e músicas"
    )
    parser.add_argument("--videos",  action="store_true",
                        help="Baixar apenas vídeos de fundo")
    parser.add_argument("--musicas", action="store_true",
                        help="Baixar apenas músicas instrumentais")
    parser.add_argument("--tema",    metavar="TEMA",
                        help=f"Baixar vídeos de um tema específico: {', '.join(TEMAS_FUNDO)}")
    parser.add_argument("--status",  action="store_true",
                        help="Mostrar o que já foi baixado")
    parser.add_argument("--minimo",  action="store_true",
                        help="Garantir mínimo de assets (chamado automaticamente)")
    parser.add_argument("--temas",   action="store_true",
                        help="Listar temas disponíveis")
    args = parser.parse_args()

    # Setup logging
    try:
        from logger_setup import get_logger
        get_logger(__name__)
    except Exception:
        logging.basicConfig(level=logging.WARNING)

    if args.status:
        mostrar_status()

    elif args.temas:
        print("\nTemas disponíveis:\n")
        for tema, info in TEMAS_FUNDO.items():
            formatos = ", ".join(info["formatos"])
            print(f"  {tema:<15} usado em: {formatos}")
        print()

    elif args.minimo:
        garantir_minimo()

    elif args.videos or args.musicas or args.tema:
        baixar_tudo(
            apenas_videos=args.videos,
            apenas_musicas=args.musicas,
            tema_especifico=args.tema,
        )

    else:
        baixar_tudo()


if __name__ == "__main__":
    main()