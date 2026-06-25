#!/usr/bin/env python3
"""
=======================================================
  BANCO DE VÍDEOS — Histórico e controle
=======================================================
  Uso:
    python banco.py --listar
    python banco.py --listar-cortes ID_DO_VIDEO
    python banco.py --stats
    python banco.py --resetar URL_OU_ID
=======================================================
"""

import sqlite3
import json
import re
import logging
import argparse
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

BANCO_ARQUIVO = "banco_shorts.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── CONEXÃO COM CONTEXT MANAGER ─────────────────────────
# FIX: antes cada função abria e fechava conn manualmente,
# sem garantia de fechar em caso de exceção (resource leak).
# Agora usamos contextmanager que garante fechamento sempre.

@contextmanager
def get_conn():
    """Context manager que garante fechamento e rollback em erro."""
    conn = sqlite3.connect(BANCO_ARQUIVO, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")  # FIX: FK não era aplicada antes
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ─── INICIALIZAÇÃO ────────────────────────────────────────

def inicializar():
    """Cria tabelas e índices se não existirem."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_id      TEXT    UNIQUE NOT NULL,
                url             TEXT    NOT NULL,
                titulo          TEXT,
                duracao_s       REAL,
                caminho_arquivo TEXT,
                transcrito      INTEGER DEFAULT 0,
                num_cortes      INTEGER DEFAULT 0,
                custo_api_usd   REAL    DEFAULT 0.0,
                criado_em       TEXT    DEFAULT (datetime('now','localtime')),
                atualizado_em   TEXT    DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS cortes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id         INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                numero           INTEGER,
                tipo             TEXT    CHECK(tipo IN ('denso','impacto','reflexao','historia','versiculo') OR tipo IS NULL),
                titulo           TEXT,
                gancho           TEXT,
                inicio_s         REAL,
                fim_s            REAL,
                duracao_s        REAL,
                caminho_video    TEXT,
                caminho_txt      TEXT,
                titulo_yt        TEXT,
                descricao        TEXT,
                hashtags         TEXT,
                status           TEXT    NOT NULL DEFAULT 'pronto'
                                         CHECK(status IN ('pronto','agendado','postado','erro')),
                agendado_para    TEXT,
                postado_em       TEXT,
                youtube_short_id TEXT,
                criado_em        TEXT    DEFAULT (datetime('now','localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_videos_yt_id  ON videos(youtube_id);
            CREATE INDEX IF NOT EXISTS idx_cortes_video  ON cortes(video_id);
            CREATE INDEX IF NOT EXISTS idx_cortes_status ON cortes(status);
            CREATE INDEX IF NOT EXISTS idx_cortes_agend  ON cortes(agendado_para)
                WHERE agendado_para IS NOT NULL;
        """)
    logger.info("Banco inicializado: %s", BANCO_ARQUIVO)

# ─── VÍDEOS ───────────────────────────────────────────────

def extrair_youtube_id(url: str) -> str:
    """Extrai o ID do vídeo de qualquer formato de URL do YouTube."""
    padroes = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})",  # FIX: aceita params extras
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for p in padroes:
        m = re.search(p, url)
        if m:
            return m.group(1)
    # FIX: retornar hash do url inteiro para IDs locais (evita colisão)
    return url

def video_ja_processado(url: str) -> dict | None:
    """Retorna o registro se já processado, None caso contrário."""
    yt_id = extrair_youtube_id(url)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE youtube_id = ? AND num_cortes > 0",
            (yt_id,)
        ).fetchone()
    return dict(row) if row else None

def registrar_video(url: str, titulo: str, duracao_s: float,
                    caminho_arquivo) -> int:
    """Registra ou atualiza um vídeo. Retorna o ID interno."""
    yt_id = extrair_youtube_id(url)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO videos (youtube_id, url, titulo, duracao_s, caminho_arquivo)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(youtube_id) DO UPDATE SET
                titulo          = excluded.titulo,
                duracao_s       = excluded.duracao_s,
                caminho_arquivo = excluded.caminho_arquivo,
                atualizado_em   = datetime('now','localtime')
        """, (yt_id, url, titulo, duracao_s, str(caminho_arquivo)))
        vid_id = conn.execute(
            "SELECT id FROM videos WHERE youtube_id = ?", (yt_id,)
        ).fetchone()["id"]
    return vid_id

def marcar_transcrito(video_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE videos SET transcrito = 1, atualizado_em = datetime('now','localtime') WHERE id = ?",
            (video_id,)
        )

def atualizar_custo(video_id: int, custo_usd: float) -> None:
    # FIX: proteção contra valores negativos
    if custo_usd < 0:
        logger.warning("Custo negativo ignorado: %.6f", custo_usd)
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE videos SET custo_api_usd = custo_api_usd + ?, atualizado_em = datetime('now','localtime') WHERE id = ?",
            (custo_usd, video_id)
        )

def listar_videos() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT v.*,
                   COUNT(c.id) AS total_cortes,
                   SUM(CASE WHEN c.status='postado' THEN 1 ELSE 0 END) AS postados
            FROM videos v
            LEFT JOIN cortes c ON c.video_id = v.id
            GROUP BY v.id
            ORDER BY v.criado_em DESC
        """).fetchall()
    return [dict(r) for r in rows]

def resetar_video(url_ou_id: str) -> None:
    """Permite reprocessar um vídeo zerando num_cortes."""
    yt_id = extrair_youtube_id(url_ou_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE videos SET num_cortes = 0, atualizado_em = datetime('now','localtime') WHERE youtube_id = ?",
            (yt_id,)
        )

# ─── CORTES ───────────────────────────────────────────────

def registrar_corte(video_id: int, numero: int, corte_info: dict,
                    caminho_video, caminho_txt, desc_info: dict | None) -> int:
    """Registra um corte gerado. Retorna o ID do corte."""
    hashtags = json.dumps(
        desc_info.get("hashtags", []), ensure_ascii=False
    ) if desc_info else "[]"

    # FIX: proteção contra None em campos float
    inicio = corte_info.get("inicio") or 0.0
    fim    = corte_info.get("fim")    or 0.0
    dur    = float(fim) - float(inicio)

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO cortes
                (video_id, numero, tipo, titulo, gancho, inicio_s, fim_s, duracao_s,
                 caminho_video, caminho_txt, titulo_yt, descricao, hashtags, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pronto')
        """, (
            video_id, numero,
            corte_info.get("tipo"),
            corte_info.get("titulo"),
            corte_info.get("gancho"),
            float(inicio), float(fim), dur,
            str(caminho_video) if caminho_video else None,
            str(caminho_txt)   if caminho_txt   else None,
            desc_info.get("titulo_yt")  if desc_info else None,
            desc_info.get("descricao")  if desc_info else None,
            hashtags,
        ))
        conn.execute(
            "UPDATE videos SET num_cortes = num_cortes + 1, atualizado_em = datetime('now','localtime') WHERE id = ?",
            (video_id,)
        )
        corte_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return corte_id

def listar_cortes(video_id: int | None = None,
                  status: str | None = None) -> list[dict]:
    # FIX: construção de query parametrizada (evita SQL injection)
    condicoes = ["1=1"]
    params: list = []
    if video_id is not None:
        condicoes.append("c.video_id = ?")
        params.append(video_id)
    if status is not None:
        condicoes.append("c.status = ?")
        params.append(status)

    query = f"""
        SELECT c.*, v.titulo AS titulo_video, v.youtube_id
        FROM cortes c
        JOIN videos v ON v.id = c.video_id
        WHERE {' AND '.join(condicoes)}
        ORDER BY c.criado_em DESC
    """
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def atualizar_status_corte(corte_id: int, status: str,
                           youtube_short_id: str | None = None) -> None:
    # FIX: validar status antes de gravar
    STATUS_VALIDOS = {"pronto", "agendado", "postado", "erro"}
    if status not in STATUS_VALIDOS:
        raise ValueError(f"Status inválido: '{status}'. Use: {STATUS_VALIDOS}")
    with get_conn() as conn:
        if youtube_short_id:
            conn.execute(
                "UPDATE cortes SET status=?, youtube_short_id=?, postado_em=datetime('now','localtime') WHERE id=?",
                (status, youtube_short_id, corte_id)
            )
        else:
            conn.execute("UPDATE cortes SET status=? WHERE id=?", (status, corte_id))

def agendar_corte(corte_id: int, data_hora_iso: str) -> None:
    """Agenda um corte (formato: 'AAAA-MM-DD HH:MM:SS')."""
    # FIX: validar formato da data antes de gravar
    try:
        datetime.strptime(data_hora_iso[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError(f"Formato de data inválido: '{data_hora_iso}'. Use 'AAAA-MM-DD HH:MM:SS'")
    with get_conn() as conn:
        conn.execute(
            "UPDATE cortes SET status='agendado', agendado_para=? WHERE id=?",
            (data_hora_iso, corte_id)
        )

def cortes_pendentes_agendamento() -> list[dict]:
    """Retorna cortes agendados cuja hora já passou."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT c.*, v.titulo AS titulo_video
            FROM cortes c
            JOIN videos v ON v.id = c.video_id
            WHERE c.status = 'agendado'
              AND c.agendado_para <= datetime('now','localtime')
            ORDER BY c.agendado_para ASC
        """).fetchall()
    return [dict(r) for r in rows]

# ─── ESTATÍSTICAS ─────────────────────────────────────────

def stats() -> dict:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT v.id)                                     AS total_videos,
                COUNT(c.id)                                              AS total_cortes,
                SUM(CASE WHEN c.status='pronto'   THEN 1 ELSE 0 END)    AS prontos,
                SUM(CASE WHEN c.status='agendado' THEN 1 ELSE 0 END)    AS agendados,
                SUM(CASE WHEN c.status='postado'  THEN 1 ELSE 0 END)    AS postados,
                SUM(CASE WHEN c.status='erro'     THEN 1 ELSE 0 END)    AS erros,
                ROUND(COALESCE(SUM(v.custo_api_usd), 0), 4)             AS custo_total_usd
            FROM videos v
            LEFT JOIN cortes c ON c.video_id = v.id
        """).fetchone()
    return dict(row)

# ─── CLI ─────────────────────────────────────────────────

def _print_videos(videos: list[dict]) -> None:
    if not videos:
        print("  Nenhum vídeo registrado.")
        return
    print(f"\n  {'ID':>4}  {'YouTube ID':>13}  {'Cortes':>6}  {'Postados':>8}  {'Custo':>8}  Título")
    print("  " + "─" * 76)
    for v in videos:
        custo = f"${v['custo_api_usd']:.3f}" if v.get("custo_api_usd") else "$0.000"
        print(f"  {v['id']:>4}  {v['youtube_id']:>13}  {v['num_cortes']:>6}  "
              f"{v.get('postados') or 0:>8}  {custo:>8}  {(v['titulo'] or '')[:38]}")

def _print_cortes(cortes: list[dict]) -> None:
    if not cortes:
        print("  Nenhum corte encontrado.")
        return
    print(f"\n  {'ID':>4}  {'Nº':>3}  {'Tipo':>8}  {'Dur':>5}  {'Status':>9}  Título")
    print("  " + "─" * 72)
    for c in cortes:
        dur = f"{c['duracao_s']:.0f}s" if c.get("duracao_s") else "—"
        print(f"  {c['id']:>4}  {c.get('numero') or 0:>3}  {c.get('tipo') or '—':>8}  "
              f"{dur:>5}  {c['status']:>9}  {(c.get('titulo') or '')[:33]}")

def main_cli() -> None:
    inicializar()
    parser = argparse.ArgumentParser(description="Banco de vídeos — controle de Shorts")
    parser.add_argument("--listar",         action="store_true")
    parser.add_argument("--listar-cortes",  metavar="VIDEO_ID")
    parser.add_argument("--listar-prontos", action="store_true")
    parser.add_argument("--stats",          action="store_true")
    parser.add_argument("--resetar",        metavar="URL_OU_ID")
    args = parser.parse_args()

    if args.listar:
        print("\n📋 VÍDEOS REGISTRADOS")
        _print_videos(listar_videos())

    elif args.listar_cortes:
        print(f"\n✂️  CORTES DO VÍDEO {args.listar_cortes}")
        _print_cortes(listar_cortes(video_id=int(args.listar_cortes)))

    elif args.listar_prontos:
        print("\n🎥 CORTES PRONTOS PARA POSTAR")
        _print_cortes(listar_cortes(status="pronto"))

    elif args.stats:
        s = stats()
        custo_brl = s["custo_total_usd"] * 5.6
        print("\n📊 ESTATÍSTICAS GERAIS")
        print(f"   Vídeos processados : {s['total_videos']}")
        print(f"   Cortes gerados     : {s['total_cortes']}")
        print(f"   Prontos p/ postar  : {s['prontos']}")
        print(f"   Agendados          : {s['agendados']}")
        print(f"   Postados           : {s['postados']}")
        print(f"   Com erro           : {s['erros']}")
        print(f"   Custo total API    : ${s['custo_total_usd']:.4f} (~R${custo_brl:.2f})")

    elif args.resetar:
        resetar_video(args.resetar)
        print(f"✓ Vídeo resetado: {args.resetar}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main_cli()