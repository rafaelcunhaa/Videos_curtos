#!/usr/bin/env python3
"""
FUNDOS DE VÍDEO POR IA (ComfyUI + LTX-Video)

Modelo de custo: a GPU roda em LOTE e gera um pool de clipes curtos (~4s)
em fundos_ia/<tema>/. A cada vídeo diário, o pipeline monta o fundo de 60s
só com FFmpeg (crossfade entre clipes sorteados) — sem GPU e sem Claude Code.

  python fundos_ia.py --gerar --dry-run          (mostra o plano, não gera)
  python fundos_ia.py --gerar --tema ceu --n 4   (GPU: ComfyUI em COMFYUI_URL)
  python fundos_ia.py --status
  python fundos_ia.py --compor 60 --saida teste.mp4   (só CPU/FFmpeg)

Ativar no pipeline: FUNDO_IA=1 no .env (fallback automático p/ fundos/ atuais).
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import requests

from comfyui_client import ComfyError, ComfyUI, carregar_workflow, preencher
from config import cfg

WORKFLOW = Path(__file__).parent / "comfy_workflows" / "ltx_t2v.json"

# LTX: largura/altura múltiplas de 32, frames = 8n+1. 544x960 = 9:16 exato.
LARGURA, ALTURA = 544, 960
FRAMES, FPS, STEPS = 97, 25, 30          # ~3.9s por clipe
CKPT = os.getenv("COMFY_LTX_CKPT", "ltx-video-2b-v0.9.5.safetensors")
CLIP = os.getenv("COMFY_LTX_CLIP", "t5xxl_fp16.safetensors")

MAX_POR_EXECUCAO = 48     # trava de custo: clipes por execução
MAX_FALHAS_SEGUIDAS = 3   # aborta cedo se o setup remoto estiver errado

NEGATIVE = ("people, faces, text, letters, watermark, logo, flicker, jitter, "
            "distorted, low quality, blurry, oversaturated, fast motion")

# Mesmos temas de fundos.py. Movimento lento e sem pessoas/texto (fundo de legenda).
PROMPTS = {
    "ceu": ["slow drifting golden clouds at sunrise, soft light rays, peaceful, cinematic, vertical",
            "soft white clouds moving over deep blue sky, gentle warm sunlight, calm, cinematic"],
    "natureza": ["lush green forest with sunbeams through trees, slow camera drift, mist, peaceful",
                 "gentle waterfall in a green valley, slow camera push in, soft light, cinematic"],
    "luz": ["golden light particles floating slowly, warm bokeh, soft glowing rays, ethereal",
            "divine sunbeams through haze, drifting dust particles, warm golden glow, slow motion"],
    "agua": ["calm ocean waves at golden hour, slow gentle motion, cinematic, peaceful",
             "clear river flowing over smooth stones, soft sunlight reflections, serene"],
    "montanha": ["majestic mountains at sunrise with moving mist, slow aerial drift, cinematic",
                 "snowy mountain peaks above clouds, soft morning light, slow camera movement"],
    "cidade_noite": ["city lights at night, soft bokeh, slow camera drift, calm, cinematic",
                     "starry night sky with slowly moving clouds, deep blue, peaceful"],
}


def _log(msg: str) -> None:
    print(f"[fundos_ia] {msg}", flush=True)


# ── Pool de clipes ─────────────────────────────────────

def listar_clips(tema: str | None = None) -> list[Path]:
    base = Path(cfg.pasta_fundos_ia)
    if not base.exists():
        return []
    pasta = base / tema if tema else base
    return sorted(pasta.glob("**/*.mp4"))


def gerar_pool(n: int = 4, tema: str | None = None, dry_run: bool = False,
               cliente: ComfyUI | None = None, limite_s: int = 900) -> list[Path]:
    """Gera n clipes por tema via ComfyUI. Cada clipe é salvo assim que fica pronto."""
    if tema and tema not in PROMPTS:
        raise ValueError(f"Tema desconhecido '{tema}'. Disponíveis: {', '.join(PROMPTS)}")
    temas = [tema] if tema else list(PROMPTS)
    total = n * len(temas)
    if total > MAX_POR_EXECUCAO:
        raise ValueError(f"{total} clipes > limite de {MAX_POR_EXECUCAO} por execução. "
                         "Reduza --n ou rode por tema (--tema).")
    if dry_run:
        _log(f"[dry-run] {total} clipes ({n} x {len(temas)} temas: {', '.join(temas)}) "
             f"{LARGURA}x{ALTURA}, {FRAMES} frames @ {FPS}fps, destino {cfg.comfyui_url}")
        return []

    cli = cliente or ComfyUI(cfg.comfyui_url, cfg.comfyui_token)
    if not cli.online():
        raise ComfyError(f"ComfyUI inacessível em {cfg.comfyui_url} (veja CLAUDE.md)")

    base = carregar_workflow(WORKFLOW)
    gerados, falhas = [], 0
    for t in temas:
        for i in range(n):
            seed = random.randrange(2**32)
            wf = preencher(base, CKPT=CKPT, CLIP=CLIP, PROMPT=PROMPTS[t][i % len(PROMPTS[t])],
                           NEGATIVE=NEGATIVE, SEED=seed, PREFIX=f"{t}_{seed}",
                           WIDTH=LARGURA, HEIGHT=ALTURA, FRAMES=FRAMES, FPS=FPS, STEPS=STEPS)
            try:
                arqs = cli.executar(wf, Path(cfg.pasta_fundos_ia) / t, limite_s=limite_s)
                gerados += arqs
                falhas = 0
                _log(f"{t} {i + 1}/{n}: {arqs[0].name}")
            except (ComfyError, requests.RequestException) as e:
                falhas += 1
                _log(f"ERRO {t} {i + 1}/{n}: {e}")
                if falhas >= MAX_FALHAS_SEGUIDAS:
                    raise ComfyError(f"{falhas} falhas seguidas — abortando para não gastar GPU") from e
    return gerados


# ── Composição do fundo longo (só FFmpeg) ──────────────

def _probe(arquivo: Path) -> tuple[float, int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(arquivo)],
        capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return float(d["format"]["duration"]), int(s["width"]), int(s["height"])


def _sequencia(clips: list[Path], durs: dict, duracao: float, fade: float) -> list[Path]:
    """Sorteia clipes sem repetir vizinhos até cobrir `duracao` (com crossfades)."""
    seq, total, fila = [], 0.0, []
    while total < duracao + 0.5:
        if not fila:
            fila = random.sample(clips, len(clips))
            if seq and len(fila) > 1 and fila[0] == seq[-1]:
                fila.append(fila.pop(0))
        c = fila.pop(0)
        total += durs[c] if not seq else durs[c] - fade
        seq.append(c)
    return seq


def compor_fundo(duracao: float, saida: Path, clips: list[Path] | None = None,
                 fade: float = 0.5) -> Path:
    clips = clips if clips is not None else listar_clips()
    if not clips:
        raise ValueError(f"Nenhum clipe em {cfg.pasta_fundos_ia} (rode --gerar)")
    info = {c: _probe(c) for c in set(clips)}
    durs = {c: v[0] for c, v in info.items()}
    _, w, h = info[clips[0]]
    fade = min(fade, min(durs.values()) / 3)

    seq = _sequencia(clips, durs, duracao, fade)
    filtros = [f"[{i}:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase,"
               f"crop={w}:{h},setsar=1,format=yuv420p[v{i}]" for i in range(len(seq))]
    rot, acum = "v0", durs[seq[0]]
    for i in range(1, len(seq)):
        off = acum - fade
        filtros.append(f"[{rot}][v{i}]xfade=transition=fade:duration={fade}:offset={off:.3f}[x{i}]")
        rot, acum = f"x{i}", off + durs[seq[i]]

    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for c in seq:
        cmd += ["-i", str(c)]
    cmd += ["-filter_complex", ";".join(filtros), "-map", f"[{rot}]",
            "-t", f"{duracao:.2f}", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(saida)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao compor fundo: {r.stderr[-300:]}")
    return saida


def obter_fundo_ia(duracao: float, pasta_tmp) -> Path | None:
    """Usado por gerador_conteudo.montar_video. Nunca levanta: se algo falhar,
    devolve None e o pipeline segue com os fundos atuais (fundos/)."""
    clips = listar_clips()
    if not clips:
        _log("FUNDO_IA=1 mas fundos_ia/ está vazio — usando fundos/ atuais")
        return None
    try:
        saida = Path(pasta_tmp) / f"fundo_ia_{os.getpid()}_{int(time.time() * 1000)}.mp4"
        return compor_fundo(duracao, saida, clips)
    except Exception as e:
        _log(f"Falha ao compor fundo IA ({e}) — usando fundos/ atuais")
        return None


# ── CLI ────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Fundos de vídeo por IA (ComfyUI + LTX)")
    p.add_argument("--gerar", action="store_true", help="Gera clipes na GPU (COMFYUI_URL)")
    p.add_argument("--tema", help=f"Um tema: {', '.join(PROMPTS)}")
    p.add_argument("--n", type=int, default=4, help="Clipes por tema (padrão 4)")
    p.add_argument("--dry-run", action="store_true", help="Só mostra o plano")
    p.add_argument("--compor", type=float, metavar="SEG", help="Compõe fundo de SEG segundos")
    p.add_argument("--saida", default="fundo_ia_teste.mp4")
    p.add_argument("--status", action="store_true")
    a = p.parse_args()

    try:
        if a.gerar:
            gerar_pool(a.n, a.tema, a.dry_run)
        elif a.compor:
            _log(f"Fundo salvo: {compor_fundo(a.compor, Path(a.saida))}")
        else:
            for t in PROMPTS:
                _log(f"{t:<14} {len(listar_clips(t))} clipe(s)")
            _log(f"ComfyUI {'online' if ComfyUI(cfg.comfyui_url, cfg.comfyui_token).online() else 'offline'}"
                 f" em {cfg.comfyui_url} | FUNDO_IA={'1' if cfg.fundo_ia else '0'}")
    except (ComfyError, ValueError, RuntimeError) as e:
        _log(f"ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
