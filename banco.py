#!/usr/bin/env python3
"""
=======================================================
  BANCO DE VÍDEOS — Histórico e controle de processamento
=======================================================
  Módulo SQLite que registra:
  • Vídeos do YouTube baixados (por URL/ID)
  • Cortes gerados por vídeo
  • Status de cada corte (processado, agendado, postado)
  • Custo de API por vídeo
  • Evita reprocessar o mesmo vídeo duas vezes

  Uso standalone:
    python banco.py --listar
    python banco.py --listar-cortes ID_DO_VIDEO
    python banco.py --stats
    python banco.py --resetar URL_OU_ID   (permite reprocessar)
=======================================================
"""

import sqlite3, json, argparse
from pathlib import Path
from datetime import datetime

BANCO_ARQUIVO = "banco_shorts.db"

# ─── INICIALIZAÇÃO ────────────────────────────────────────

def conectar():
    conn = sqlite3.connect(BANCO_ARQUIVO)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def inicializar():
    """Cria as tabelas se não existirem"""
    conn = conectar()
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
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id        INTEGER NOT NULL REFERENCES videos(id),
            numero          INTEGER,
            tipo            TEXT,
            titulo          TEXT,
            gancho          TEXT,
            inicio_s        REAL,
            fim_s           REAL,
            duracao_s       REAL,
            caminho_video   TEXT,
            caminho_txt     TEXT,
            titulo_yt       TEXT,
            descricao       TEXT,
            hashtags        TEXT,
            status          TEXT    DEFAULT 'pronto',
            agendado_para   TEXT,
            postado_em      TEXT,
            youtube_short_id TEXT,
            criado_em       TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_videos_yt_id ON videos(youtube_id);
        CREATE INDEX IF NOT EXISTS idx_cortes_video ON cortes(video_id);
        CREATE INDEX IF NOT EXISTS idx_cortes_status ON cortes(status);
    """)
    conn.commit()
    conn.close()

# ─── VÍDEOS ───────────────────────────────────────────────

def extrair_youtube_id(url):
    """Extrai o ID do vídeo de qualquer formato de URL do YouTube"""
    import re
    padroes = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for p in padroes:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return url  # retorna a própria string se não encontrar padrão

def video_ja_processado(url):
    """Retorna o registro do vídeo se já foi processado, None caso contrário"""
    yt_id = extrair_youtube_id(url)
    conn  = conectar()
    row   = conn.execute(
        "SELECT * FROM videos WHERE youtube_id = ? AND num_cortes > 0",
        (yt_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def registrar_video(url, titulo, duracao_s, caminho_arquivo):
    """Registra ou atualiza um vídeo no banco"""
    yt_id = extrair_youtube_id(url)
    conn  = conectar()
    conn.execute("""
        INSERT INTO videos (youtube_id, url, titulo, duracao_s, caminho_arquivo)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(youtube_id) DO UPDATE SET
            titulo          = excluded.titulo,
            duracao_s       = excluded.duracao_s,
            caminho_arquivo = excluded.caminho_arquivo,
            atualizado_em   = datetime('now','localtime')
    """, (yt_id, url, titulo, duracao_s, str(caminho_arquivo)))
    conn.commit()
    vid_id = conn.execute(
        "SELECT id FROM videos WHERE youtube_id = ?", (yt_id,)
    ).fetchone()["id"]
    conn.close()
    return vid_id

def marcar_transcrito(video_id):
    conn = conectar()
    conn.execute(
        "UPDATE videos SET transcrito = 1, atualizado_em = datetime('now','localtime') WHERE id = ?",
        (video_id,)
    )
    conn.commit()
    conn.close()

def atualizar_custo(video_id, custo_usd):
    conn = conectar()
    conn.execute(
        "UPDATE videos SET custo_api_usd = custo_api_usd + ?, atualizado_em = datetime('now','localtime') WHERE id = ?",
        (custo_usd, video_id)
    )
    conn.commit()
    conn.close()

def buscar_video_por_id(video_id):
    conn = conectar()
    row  = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def listar_videos():
    conn  = conectar()
    rows  = conn.execute("""
        SELECT v.*, COUNT(c.id) as total_cortes,
               SUM(CASE WHEN c.status='postado' THEN 1 ELSE 0 END) as postados
        FROM videos v
        LEFT JOIN cortes c ON c.video_id = v.id
        GROUP BY v.id
        ORDER BY v.criado_em DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def resetar_video(url_ou_id):
    """Permite reprocessar um vídeo (zera num_cortes)"""
    conn  = conectar()
    yt_id = extrair_youtube_id(url_ou_id)
    conn.execute(
        "UPDATE videos SET num_cortes = 0, atualizado_em = datetime('now','localtime') WHERE youtube_id = ?",
        (yt_id,)
    )
    conn.commit()
    conn.close()

# ─── CORTES ───────────────────────────────────────────────

def registrar_corte(video_id, numero, corte_info, caminho_video, caminho_txt, desc_info):
    """Registra um corte gerado no banco"""
    conn     = conectar()
    hashtags = json.dumps(desc_info.get("hashtags", []), ensure_ascii=False) if desc_info else "[]"
    conn.execute("""
        INSERT INTO cortes
            (video_id, numero, tipo, titulo, gancho, inicio_s, fim_s, duracao_s,
             caminho_video, caminho_txt, titulo_yt, descricao, hashtags, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pronto')
    """, (
        video_id,
        numero,
        corte_info.get("tipo"),
        corte_info.get("titulo"),
        corte_info.get("gancho"),
        corte_info.get("inicio"),
        corte_info.get("fim"),
        float(corte_info.get("fim", 0)) - float(corte_info.get("inicio", 0)),
        str(caminho_video) if caminho_video else None,
        str(caminho_txt)   if caminho_txt   else None,
        desc_info.get("titulo_yt")   if desc_info else None,
        desc_info.get("descricao")   if desc_info else None,
        hashtags,
    ))
    conn.execute(
        "UPDATE videos SET num_cortes = num_cortes + 1, atualizado_em = datetime('now','localtime') WHERE id = ?",
        (video_id,)
    )
    conn.commit()
    corte_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return corte_id

def listar_cortes(video_id=None, status=None):
    conn  = conectar()
    query = """
        SELECT c.*, v.titulo as titulo_video, v.youtube_id
        FROM cortes c
        JOIN videos v ON v.id = c.video_id
        WHERE 1=1
    """
    params = []
    if video_id:
        query  += " AND c.video_id = ?"
        params.append(video_id)
    if status:
        query  += " AND c.status = ?"
        params.append(status)
    query += " ORDER BY c.criado_em DESC"
    rows  = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_status_corte(corte_id, status, youtube_short_id=None):
    conn = conectar()
    if youtube_short_id:
        conn.execute(
            "UPDATE cortes SET status = ?, youtube_short_id = ?, postado_em = datetime('now','localtime') WHERE id = ?",
            (status, youtube_short_id, corte_id)
        )
    else:
        conn.execute("UPDATE cortes SET status = ? WHERE id = ?", (status, corte_id))
    conn.commit()
    conn.close()

def agendar_corte(corte_id, data_hora_iso):
    """Agenda um corte para postagem (formato: 2026-06-25 14:30:00)"""
    conn = conectar()
    conn.execute(
        "UPDATE cortes SET status = 'agendado', agendado_para = ? WHERE id = ?",
        (data_hora_iso, corte_id)
    )
    conn.commit()
    conn.close()

def cortes_pendentes_agendamento():
    """Retorna cortes agendados cuja hora já passou"""
    conn = conectar()
    rows = conn.execute("""
        SELECT c.*, v.titulo as titulo_video
        FROM cortes c
        JOIN videos v ON v.id = c.video_id
        WHERE c.status = 'agendado'
          AND c.agendado_para <= datetime('now','localtime')
        ORDER BY c.agendado_para ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── ESTATÍSTICAS ─────────────────────────────────────────

def stats():
    conn   = conectar()
    totais = conn.execute("""
        SELECT
            COUNT(DISTINCT v.id)                                        as total_videos,
            COUNT(c.id)                                                 as total_cortes,
            SUM(CASE WHEN c.status = 'pronto'    THEN 1 ELSE 0 END)    as prontos,
            SUM(CASE WHEN c.status = 'agendado'  THEN 1 ELSE 0 END)    as agendados,
            SUM(CASE WHEN c.status = 'postado'   THEN 1 ELSE 0 END)    as postados,
            ROUND(SUM(v.custo_api_usd), 4)                             as custo_total_usd
        FROM videos v
        LEFT JOIN cortes c ON c.video_id = v.id
    """).fetchone()
    conn.close()
    return dict(totais)

# ─── CLI STANDALONE ───────────────────────────────────────

def _imprimir_videos(videos):
    if not videos:
        print("  Nenhum vídeo registrado.")
        return
    print(f"\n{'ID':>4}  {'YouTube ID':>12}  {'Cortes':>6}  {'Postados':>8}  {'Custo':>8}  Título")
    print("─" * 80)
    for v in videos:
        custo = f"${v['custo_api_usd']:.3f}" if v['custo_api_usd'] else "$0.000"
        print(f"  {v['id']:>4}  {v['youtube_id']:>12}  {v['num_cortes']:>6}  "
              f"{v.get('postados') or 0:>8}  {custo:>8}  {(v['titulo'] or '')[:40]}")

def _imprimir_cortes(cortes):
    if not cortes:
        print("  Nenhum corte encontrado.")
        return
    print(f"\n{'ID':>4}  {'Nº':>3}  {'Tipo':>6}  {'Dur':>4}  {'Status':>9}  Título")
    print("─" * 75)
    for c in cortes:
        dur = f"{c['duracao_s']:.0f}s" if c['duracao_s'] else "—"
        print(f"  {c['id']:>4}  {c['numero'] or 0:>3}  {c['tipo'] or '—':>6}  "
              f"{dur:>4}  {c['status']:>9}  {(c['titulo'] or '')[:35]}")

def main_cli():
    inicializar()
    parser = argparse.ArgumentParser(description="Banco de vídeos — controle de Shorts")
    parser.add_argument("--listar",         action="store_true", help="Lista todos os vídeos")
    parser.add_argument("--listar-cortes",  metavar="VIDEO_ID",  help="Lista cortes de um vídeo")
    parser.add_argument("--listar-prontos", action="store_true", help="Lista cortes prontos para postar")
    parser.add_argument("--stats",          action="store_true", help="Resumo geral")
    parser.add_argument("--resetar",        metavar="URL_OU_ID", help="Permite reprocessar um vídeo")
    args = parser.parse_args()

    if args.listar:
        print("\n📋 VÍDEOS REGISTRADOS")
        _imprimir_videos(listar_videos())

    elif args.listar_cortes:
        print(f"\n✂️  CORTES DO VÍDEO {args.listar_cortes}")
        _imprimir_cortes(listar_cortes(video_id=int(args.listar_cortes)))

    elif args.listar_prontos:
        print("\n🎥 CORTES PRONTOS PARA POSTAR")
        _imprimir_cortes(listar_cortes(status="pronto"))

    elif args.stats:
        s = stats()
        custo_brl = (s['custo_total_usd'] or 0) * 5.6
        print("\n📊 ESTATÍSTICAS GERAIS")
        print(f"   Vídeos processados : {s['total_videos']}")
        print(f"   Cortes gerados     : {s['total_cortes']}")
        print(f"   Prontos p/ postar  : {s['prontos']}")
        print(f"   Agendados          : {s['agendados']}")
        print(f"   Postados           : {s['postados']}")
        print(f"   Custo total API    : ${s['custo_total_usd'] or 0:.4f} (~R${custo_brl:.2f})")

    elif args.resetar:
        resetar_video(args.resetar)
        print(f"✓ Vídeo resetado — pode ser reprocessado: {args.resetar}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main_cli()