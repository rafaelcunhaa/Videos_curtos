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
    python banco.py --temas
    python banco.py --importar-output (importar vídeos existentes da pasta output para o banco)
=======================================================
"""
import subprocess
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
                categoria        TEXT CHECK(categoria IN ('podcast','ia') OR categoria IS NULL),
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

        -- Deduplicação de temas gerados
        CREATE TABLE IF NOT EXISTS temas_usados (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo       TEXT NOT NULL,   -- reflexao | historia | versiculo
            tema       TEXT NOT NULL,
            usado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(tipo, tema)
        );
        CREATE INDEX IF NOT EXISTS idx_temas_tipo ON temas_usados(tipo);
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
                (video_id, numero, tipo, categoria, titulo, gancho, inicio_s, fim_s, duracao_s,
                 caminho_video, caminho_txt, titulo_yt, descricao, hashtags, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_id, numero,
            corte_info.get("tipo"),
            corte_info.get("categoria"),
            corte_info.get("titulo"),
            corte_info.get("gancho"),
            float(inicio), float(fim), dur,
            str(caminho_video) if caminho_video else None,
            str(caminho_txt)   if caminho_txt   else None,
            desc_info.get("titulo_yt")  if desc_info else None,
            desc_info.get("descricao")  if desc_info else None,
            hashtags,
            "pronto"
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

    # nosec B608 — 'condicoes' só recebe strings literais fixas do código-fonte
    # (nunca dado externo); os valores reais (video_id, status) vão em 'params'
    # e são passados como segundo argumento de conn.execute(), que é a API
    # parametrizada do sqlite3. O f-string monta apenas a cláusula WHERE com
    # placeholders '?' — nenhum valor de usuário é interpolado direto na string.
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

def limpar_agendamentos() -> int:
    """
    Remove todos os agendamentos futuros.
    Não altera vídeos já postados.
    Retorna quantos cortes foram resetados.
    """
    with get_conn() as conn:

        cur = conn.execute("""
            UPDATE cortes
               SET status='pronto',
                   agendado_para=NULL
             WHERE status='agendado'
        """)

        return cur.rowcount

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

# ─── DEDUPLICAÇÃO DE TEMAS ──────────────────────────────

def registrar_tema_usado(tipo: str, tema: str) -> None:
    """Registra um tema como usado para evitar repetição futura."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO temas_usados (tipo, tema) VALUES (?, ?)",
            (tipo, tema)
        )

def temas_ja_usados(tipo: str) -> set[str]:
    """Retorna conjunto de temas já usados para um tipo."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tema FROM temas_usados WHERE tipo = ?", (tipo,)
        ).fetchall()
    return {r["tema"] for r in rows}

def proximo_tema_disponivel(tipo: str, todos_os_temas: list[str]) -> str:
    """
    Retorna o próximo tema não usado.
    Se todos já foram usados, reseta o ciclo e recomeça.
    """
    import random
    usados = temas_ja_usados(tipo)
    disponiveis = [t for t in todos_os_temas if t not in usados]

    if not disponiveis:
        # Todos usados — resetar ciclo
        logger.info("Todos os temas '%s' já foram usados — reiniciando ciclo", tipo)
        with get_conn() as conn:
            conn.execute("DELETE FROM temas_usados WHERE tipo = ?", (tipo,))
        disponiveis = todos_os_temas[:]

    escolhido = random.choice(disponiveis)
    registrar_tema_usado(tipo, escolhido)
    return escolhido

def stats_temas() -> dict:
    """Retorna quantos temas já foram usados por tipo."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT tipo, COUNT(*) as total
            FROM temas_usados
            GROUP BY tipo
        """).fetchall()
    return {r["tipo"]: r["total"] for r in rows}

def parse_txt(txt_path: Path) -> dict:
    """
    Lê o arquivo .txt do vídeo e extrai todas as informações.
    """

    texto = txt_path.read_text(encoding="utf-8", errors="ignore")

    def extrair(bloco_inicio, proximo_bloco=None):
        if bloco_inicio not in texto:
            return ""

        parte = texto.split(bloco_inicio, 1)[1]

        if proximo_bloco and proximo_bloco in parte:
            parte = parte.split(proximo_bloco, 1)[0]

        return parte.strip()

    titulo = extrair("TÍTULO:", "DESCRIÇÃO:")
    descricao = extrair("DESCRIÇÃO:", "HASHTAGS:")
    hashtags = extrair("HASHTAGS:", "=== TIKTOK ===")

    formato = ""
    tema = ""

    if "=== INFO ===" in texto:

        info = texto.split("=== INFO ===", 1)[1]

        for linha in info.splitlines():

            linha = linha.strip()

            if linha.startswith("FORMATO:"):
                formato = linha.replace("FORMATO:", "").strip().lower()

            elif linha.startswith("TEMA:"):
                tema = linha.replace("TEMA:", "").strip()

    return {
        "titulo": titulo,
        "descricao": descricao,
        "hashtags": hashtags.split(),
        "formato": formato,
        "tema": tema
    }

def detectar_tipo(nome: str) -> str:

    nome = nome.lower()

    if nome.startswith("reflexao"):
        return "reflexao"

    if nome.startswith("historia"):
        return "historia"

    if nome.startswith("versiculo"):
        return "versiculo"

    if "_impacto_" in nome:
        return "impacto"

    if "_denso_" in nome:
        return "denso"

    return "denso"

def obter_duracao_video(video: Path) -> float:

    try:

        resultado = subprocess.run(

            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
        )

        return float(resultado.stdout.strip())

    except Exception:

        return 0.0
    
def importar_video(video_path: Path):

    txt = video_path.with_suffix(".txt")

    if not txt.exists():
        logger.warning("TXT não encontrado: %s", video_path.name)
        return False

    youtube_id = f"gerado_{video_path.stem}"

    with get_conn() as conn:

        existe = conn.execute(
            "SELECT id FROM videos WHERE youtube_id=?",
            (youtube_id,)
        ).fetchone()

    if existe:
        logger.info("%s já está no banco.", video_path.name)
        return False

    info = parse_txt(txt)

    duracao = obter_duracao_video(video_path)

    video_id = registrar_video(
        url=youtube_id,
        titulo=info["titulo"],
        duracao_s=duracao,
        caminho_arquivo=video_path
    )

    registrar_corte(
        video_id=video_id,
        numero=1,
        corte_info={
            "tipo": detectar_tipo(video_path.name),
            "categoria": "ia",
            "titulo": info["titulo"],
            "gancho": "",
            "inicio": 0,
            "fim": duracao
        },
        caminho_video=video_path,
        caminho_txt=txt,
        desc_info={
            "titulo_yt": info["titulo"],
            "descricao": info["descricao"],
            "hashtags": info["hashtags"]
        }
    )

    logger.info("Importado: %s", video_path.name)

    return True

def importar_output():

    pasta = Path("output")

    if not pasta.exists():
        print("Pasta output não encontrada.")
        return

    videos = sorted(pasta.glob("*.mp4"))

    total = 0
    ignorados = 0

    print("\n========== IMPORTAÇÃO ==========\n")

    for video in videos:

        try:

            if importar_video(video):
                total += 1
            else:
                ignorados += 1

        except Exception as e:

            logger.exception("Erro importando %s", video.name)

    print("\n==============================")
    print(f"Importados : {total}")
    print(f"Ignorados  : {ignorados}")
    print("==============================")

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
    parser.add_argument("--temas",          action="store_true",
                        help="Mostra quantos temas já foram usados por tipo")
    parser.add_argument("--importar-output",action="store_true",help="Importa vídeos existentes da pasta output para o banco.")
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

    elif args.temas:
        s = stats_temas()
        print("\n📋 TEMAS JÁ USADOS\n")
        for tipo, total in s.items():
            print(f"   {tipo:<12}: {total} temas usados")
        if not s:
            print("   Nenhum tema registrado ainda.")
        print()

    elif args.importar_output:
        importar_output()

    else:
        parser.print_help()

if __name__ == "__main__":
    main_cli()