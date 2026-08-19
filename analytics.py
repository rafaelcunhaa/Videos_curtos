#!/usr/bin/env python3
"""
=======================================================
  ANÁLISE DE PERFORMANCE — YouTube Shorts + IA
=======================================================
  Busca métricas reais de cada Short via YouTube Analytics
  API, salva no banco e usa IA para identificar padrões
  e ajustar automaticamente o conteúdo futuro.

  O QUE FAZ:
  1. Busca views, likes, comentários, retenção de cada Short
  2. Salva métricas no banco por data (histórico)
  3. IA analisa os dados e identifica:
       • Quais formatos performam melhor (reflexão, história...)
       • Quais temas geram mais engajamento
       • Melhor horário de postagem
       • Padrões nos ganchos que retêm mais
  4. Gera recomendações que o gerador_conteudo.py usa

  CONFIGURAÇÃO:
  - Mesma conta OAuth do agendador.py (credentials.json)
  - Habilitar "YouTube Analytics API" no Google Cloud Console

  USO:
    python analytics.py                    (analisar e recomendar)
    python analytics.py --coletar          (só coleta métricas)
    python analytics.py --relatorio        (relatório detalhado)
    python analytics.py --top 10           (top 10 vídeos)
    python analytics.py --recomendacoes    (só as recomendações da IA)
=======================================================
"""

import json
import logging
import sys
import re
import argparse
import anthropic
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional
from retry import chamar_anthropic
import banco
from config import cfg
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    Credentials = None
    Request = None
    build = None

logger = logging.getLogger(__name__)

# ── Tabela de métricas no banco ───────────────────────────
SQL_CRIAR_METRICAS = """
CREATE TABLE IF NOT EXISTS metricas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    corte_id      INTEGER NOT NULL REFERENCES cortes(id) ON DELETE CASCADE,
    coletado_em   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    data_ref      TEXT    NOT NULL,
    views         INTEGER DEFAULT 0,
    likes         INTEGER DEFAULT 0,
    comentarios   INTEGER DEFAULT 0,
    compartilhamentos INTEGER DEFAULT 0,
    minutos_assistidos REAL DEFAULT 0.0,
    retencao_pct  REAL DEFAULT 0.0,
    ctr_pct       REAL DEFAULT 0.0,
    inscritos_ganhos INTEGER DEFAULT 0,
    UNIQUE(corte_id, data_ref)
);

CREATE TABLE IF NOT EXISTS recomendacoes_ia (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gerado_em     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    tipo          TEXT,
    conteudo      TEXT    NOT NULL,
    aplicado      INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_metricas_corte ON metricas(corte_id);
CREATE INDEX IF NOT EXISTS idx_metricas_data  ON metricas(data_ref);
"""


def _garantir_tabelas():
    """Cria tabelas de métricas se não existirem."""
    with banco.get_conn() as conn:
        conn.executescript(SQL_CRIAR_METRICAS)


# ── COLETA DE MÉTRICAS ────────────────────────────────────

def _autenticar_youtube():
    """Reutiliza autenticação do agendador."""
    if not Credentials or not Request or not build:
        logger.error("google-auth / googleapiclient não instalados")
        return None, None

    TOKEN_FILE = "token.json"
    SCOPES     = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
    ]

    if not Path(TOKEN_FILE).exists():
        logger.error("token.json não encontrado — rode: python agendador.py --auth")
        return None, None

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(TOKEN_FILE).write_text(creds.to_json())

    yt        = build("youtube",          "v3",          credentials=creds)
    analytics = build("youtubeAnalytics", "v2",          credentials=creds)
    return yt, analytics


def _obter_channel_id(yt) -> Optional[str]:
    """Retorna o channel_id da conta autenticada."""
    # yt is a googleapiclient.discovery.Resource; typed as Any to avoid heavy import
    try:
        res = yt.channels().list(part="id", mine=True).execute()
        items = res.get("items", [])
        if items:
            return items[0]["id"]
    except Exception as e:
        logger.error("Erro ao obter channel_id: %s", e)
    return None


def _buscar_metricas_video(analytics, channel_id: str,
                            video_id: str,
                            data_inicio: str,
                            data_fim: str) -> dict:
    """
    Busca métricas de um vídeo específico via YouTube Analytics API.
    Retorna dict com todas as métricas ou vazio em falha.
    """
    # analytics is a googleapiclient.discovery.Resource
    try:
        res = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=data_inicio,
            endDate=data_fim,
            metrics=",".join([
                "views",
                "likes",
                "comments",
                "shares",
                "estimatedMinutesWatched",
                "averageViewPercentage",
                "subscribersGained",
                "annotationClickThroughRate",
            ]),
            filters=f"video=={video_id}",
            dimensions="video",
        ).execute()

        rows = res.get("rows", [])
        if not rows:
            return {}

        row = rows[0]
        # Ordem: video, views, likes, comments, shares,
        #        estimatedMinutesWatched, averageViewPercentage,
        #        subscribersGained, annotationClickThroughRate
        return {
            "views":               int(row[1])   if len(row) > 1 else 0,
            "likes":               int(row[2])   if len(row) > 2 else 0,
            "comentarios":         int(row[3])   if len(row) > 3 else 0,
            "compartilhamentos":   int(row[4])   if len(row) > 4 else 0,
            "minutos_assistidos":  float(row[5]) if len(row) > 5 else 0.0,
            "retencao_pct":        float(row[6]) if len(row) > 6 else 0.0,
            "inscritos_ganhos":    int(row[7])   if len(row) > 7 else 0,
            "ctr_pct":             float(row[8]) if len(row) > 8 else 0.0,
        }

    except Exception as e:
        logger.warning("Erro ao buscar métricas do vídeo %s: %s", video_id, e)
        return {}


def coletar_metricas(dias_atras: int = 28) -> dict:
    """
    Coleta métricas de todos os Shorts postados via YouTube Analytics.
    Busca os últimos N dias de dados.
    Retorna resumo da coleta.
    """
    _garantir_tabelas()

    banco.inicializar()

    resultado = {"coletados": 0, "erros": 0, "sem_dados": 0}

    # Buscar cortes postados com youtube_short_id
    with banco.get_conn() as conn:
        cortes = conn.execute("""
            SELECT c.id, c.youtube_short_id, c.titulo, c.tipo,
                   c.duracao_s, c.postado_em, c.gancho
            FROM cortes c
            WHERE c.status = 'postado'
              AND c.youtube_short_id IS NOT NULL
              AND c.youtube_short_id != ''
            ORDER BY c.postado_em DESC
        """).fetchall()

    if not cortes:
        logger.info("Nenhum Short postado com ID do YouTube ainda")
        print("  Nenhum Short postado com ID do YouTube ainda.")
        return resultado

    print(f"  Coletando métricas de {len(cortes)} Short(s)...\n")

    yt, analytics = _autenticar_youtube()
    if not yt:
        return resultado

    channel_id = _obter_channel_id(yt)
    if not channel_id:
        logger.error("Não foi possível obter o channel_id")
        return resultado

    data_fim    = date.today().isoformat()
    data_inicio = (date.today() - timedelta(days=dias_atras)).isoformat()

    for corte in cortes:
        corte_id  = corte["id"]
        video_id  = corte["youtube_short_id"]
        titulo    = (corte["titulo"] or "—")[:40]

        print(f"  [{corte_id}] {titulo}...", end="", flush=True)

        metricas = _buscar_metricas_video(
            analytics, channel_id, video_id,
            data_inicio, data_fim
        )

        if not metricas:
            print(" sem dados")
            resultado["sem_dados"] += 1
            continue

        # Salvar no banco
        try:
            with banco.get_conn() as conn:
                conn.execute("""
                    INSERT INTO metricas
                        (corte_id, data_ref, views, likes, comentarios,
                         compartilhamentos, minutos_assistidos,
                         retencao_pct, ctr_pct, inscritos_ganhos)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(corte_id, data_ref) DO UPDATE SET
                        views                = excluded.views,
                        likes                = excluded.likes,
                        comentarios          = excluded.comentarios,
                        compartilhamentos    = excluded.compartilhamentos,
                        minutos_assistidos   = excluded.minutos_assistidos,
                        retencao_pct         = excluded.retencao_pct,
                        ctr_pct              = excluded.ctr_pct,
                        inscritos_ganhos     = excluded.inscritos_ganhos,
                        coletado_em          = datetime('now','localtime')
                """, (
                    corte_id, data_fim,
                    metricas["views"],
                    metricas["likes"],
                    metricas["comentarios"],
                    metricas["compartilhamentos"],
                    metricas["minutos_assistidos"],
                    metricas["retencao_pct"],
                    metricas["ctr_pct"],
                    metricas["inscritos_ganhos"],
                ))
            print(f" {metricas['views']:,} views | {metricas['retencao_pct']:.0f}% retenção")
            resultado["coletados"] += 1

        except Exception as e:
            print(f" erro: {e}")
            resultado["erros"] += 1
            logger.error("Erro ao salvar métricas do corte %d: %s", corte_id, e)

    return resultado


# ── ANÁLISE COM IA ────────────────────────────────────────

def _carregar_dados_para_analise() -> dict:
    """Carrega todos os dados de métricas para análise."""
    
    with banco.get_conn() as conn:
        # Dados por formato
        por_formato = conn.execute("""
            SELECT
                c.tipo,
                COUNT(*)                        AS total,
                AVG(m.views)                    AS avg_views,
                AVG(m.likes)                    AS avg_likes,
                AVG(m.retencao_pct)             AS avg_retencao,
                AVG(m.inscritos_ganhos)         AS avg_inscritos,
                SUM(m.views)                    AS total_views,
                MAX(m.views)                    AS max_views
            FROM cortes c
            JOIN metricas m ON m.corte_id = c.id
            WHERE c.tipo IS NOT NULL
            GROUP BY c.tipo
            ORDER BY avg_views DESC
        """).fetchall()

        # Top 10 vídeos por views
        top_videos = conn.execute("""
            SELECT
                c.titulo,
                c.tipo,
                c.gancho,
                c.duracao_s,
                m.views,
                m.likes,
                m.retencao_pct,
                m.inscritos_ganhos,
                c.postado_em
            FROM cortes c
            JOIN metricas m ON m.corte_id = c.id
            ORDER BY m.views DESC
            LIMIT 10
        """).fetchall()

        # Piores 5 (para evitar)
        piores = conn.execute("""
            SELECT c.titulo, c.tipo, c.gancho, m.views, m.retencao_pct
            FROM cortes c
            JOIN metricas m ON m.corte_id = c.id
            ORDER BY m.views ASC
            LIMIT 5
        """).fetchall()

        # Performance por dia da semana / hora
        por_horario = conn.execute("""
            SELECT
                CAST(strftime('%H', c.postado_em) AS INTEGER) AS hora,
                AVG(m.views)   AS avg_views,
                COUNT(*)       AS total
            FROM cortes c
            JOIN metricas m ON m.corte_id = c.id
            WHERE c.postado_em IS NOT NULL
            GROUP BY hora
            ORDER BY avg_views DESC
            LIMIT 5
        """).fetchall()

        # Análise de ganchos vs retenção
        ganchos = conn.execute("""
            SELECT c.gancho, c.tipo, m.views, m.retencao_pct
            FROM cortes c
            JOIN metricas m ON m.corte_id = c.id
            WHERE c.gancho IS NOT NULL
              AND m.views > 0
            ORDER BY m.retencao_pct DESC
            LIMIT 20
        """).fetchall()

    return {
        "por_formato": [dict(r) for r in por_formato],
        "top_videos":  [dict(r) for r in top_videos],
        "piores":      [dict(r) for r in piores],
        "por_horario": [dict(r) for r in por_horario],
        "ganchos":     [dict(r) for r in ganchos],
    }


def analisar_com_ia() -> Optional[dict]:
    """
    Envia métricas para Claude analisar e gerar recomendações.
    Salva recomendações no banco para uso pelo gerador_conteudo.py
    """
    _garantir_tabelas()
    banco.inicializar()

    dados = _carregar_dados_para_analise()

    # Verificar se há dados suficientes
    total_metricas = sum(len(v) for v in dados.values() if isinstance(v, list))
    if total_metricas == 0:
        print("  Nenhuma métrica coletada ainda. Rode --coletar primeiro.")
        return None

    if not cfg.chave_anthropic:
        print("  ANTHROPIC_API_KEY não configurada.")
        return None

    print("  🤖 IA analisando performance...\n")

    # Formatar dados para o prompt
    dados_texto = json.dumps(dados, ensure_ascii=False, indent=2, default=str)

    cliente = anthropic.Anthropic(api_key=cfg.chave_anthropic)
    prompt  = f"""Você é um especialista em estratégia de conteúdo para TikTok e YouTube Shorts,
com foco em canais religiosos brasileiros.

Analise as métricas de performance abaixo e forneça recomendações estratégicas
para maximizar views, retenção e crescimento de inscritos.

MÉTRICAS DO CANAL:
{dados_texto}

Com base nesses dados, responda SOMENTE com JSON puro no formato abaixo.
Seja específico e baseado nos dados — não genérico.

{{
  "resumo": "2-3 frases resumindo a situação geral do canal",
  "melhor_formato": {{
    "tipo": "reflexao | historia | versiculo | denso | impacto",
    "motivo": "explicação baseada nos dados",
    "prioridade": "alta | media | baixa"
  }},
  "piores_formatos": ["tipo1", "tipo2"],
  "melhor_horario": {{
    "hora": 18,
    "motivo": "explicação baseada nos dados"
  }},
  "padroes_gancho": {{
    "funciona": "padrão de gancho que gera mais retenção",
    "evitar": "padrão de gancho que gera menos retenção"
  }},
  "temas_recomendados": [
    "tema específico 1 baseado no que performou bem",
    "tema específico 2",
    "tema específico 3"
  ],
  "temas_evitar": [
    "tema que não performou"
  ],
  "duracao_ideal": {{
    "segundos": 75,
    "motivo": "baseado na retenção média"
  }},
  "acoes_imediatas": [
    "ação concreta 1 para implementar esta semana",
    "ação concreta 2",
    "ação concreta 3"
  ],
  "meta_proxima_semana": "meta específica e realista baseada nos dados atuais"
}}"""

    try:
        resposta = chamar_anthropic(
            cliente.messages.create,
            model=cfg.modelo_claude,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        texto = re.sub(r"```json|```", "", resposta.content[0].text.strip()).strip()
        recomendacoes = json.loads(texto)

        # Salvar no banco
        with banco.get_conn() as conn:
            conn.execute("""
                INSERT INTO recomendacoes_ia (tipo, conteudo)
                VALUES ('analise_performance', ?)
            """, (json.dumps(recomendacoes, ensure_ascii=False),))

        logger.info("Recomendações da IA salvas no banco")
        return recomendacoes

    except Exception as e:
        logger.error("Erro na análise da IA: %s", e, exc_info=True)
        print(f"  Erro na análise: {e}")
        return None


def obter_ultima_recomendacao() -> Optional[dict]:
    """Retorna a última recomendação da IA salva no banco."""
    _garantir_tabelas()

    try:
        with banco.get_conn() as conn:
            row = conn.execute("""
                SELECT conteudo, gerado_em
                FROM recomendacoes_ia
                WHERE tipo = 'analise_performance'
                ORDER BY gerado_em DESC
                LIMIT 1
            """).fetchone()

        if row:
            return {
                "dados":      json.loads(row["conteudo"]),
                "gerado_em":  row["gerado_em"],
            }
    except Exception as e:
        logger.warning("Erro ao buscar recomendação: %s", e)

    return None


# ── RELATÓRIOS ────────────────────────────────────────────

def imprimir_relatorio():
    """Imprime relatório completo de performance."""
    _garantir_tabelas()
    banco.inicializar()

    dados = _carregar_dados_para_analise()

    print("\n" + "═"*65)
    print("  RELATÓRIO DE PERFORMANCE — YouTube Shorts")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("═"*65)

    # Performance por formato
    if dados["por_formato"]:
        print("\n📊 PERFORMANCE POR FORMATO\n")
        print(f"  {'Formato':<12} {'Vídeos':>6} {'Avg Views':>10} {'Retenção':>9} {'Inscritos':>10}")
        print("  " + "─"*55)
        for f in dados["por_formato"]:
            print(
                f"  {(f['tipo'] or '—'):<12} {f['total']:>6} "
                f"{f['avg_views']:>10.0f} {f['avg_retencao']:>8.1f}% "
                f"{f['avg_inscritos']:>10.1f}"
            )

    # Top vídeos
    if dados["top_videos"]:
        print("\n🏆 TOP 10 VÍDEOS\n")
        print(f"  {'#':>2}  {'Views':>8}  {'Ret%':>5}  {'Tipo':<8}  Título")
        print("  " + "─"*60)
        for i, v in enumerate(dados["top_videos"], 1):
            titulo = (v["titulo"] or "—")[:30]
            print(
                f"  {i:>2}  {v['views']:>8,}  {v['retencao_pct']:>5.1f}%  "
                f"{(v['tipo'] or '—'):<8}  {titulo}"
            )

    # Melhores horários
    if dados["por_horario"]:
        print("\n🕐 MELHORES HORÁRIOS DE POSTAGEM\n")
        for h in dados["por_horario"]:
            barra = "█" * min(int(h["avg_views"] / 1000), 30)
            print(f"  {h['hora']:02d}h  {barra}  {h['avg_views']:,.0f} views avg")

    # Última recomendação da IA
    rec = obter_ultima_recomendacao()
    if rec:
        dados_rec = rec["dados"]
        print(f"\n🤖 ÚLTIMA ANÁLISE DA IA ({rec['gerado_em']})\n")
        print(f"  Resumo: {dados_rec.get('resumo','—')}\n")

        melhor = dados_rec.get("melhor_formato", {})
        if melhor:
            print(f"  ✅ Melhor formato: {melhor.get('tipo','—').upper()}")
            print(f"     {melhor.get('motivo','')}\n")

        horario = dados_rec.get("melhor_horario", {})
        if horario:
            print(f"  🕐 Melhor horário: {horario.get('hora',0):02d}h")
            print(f"     {horario.get('motivo','')}\n")

        acoes = dados_rec.get("acoes_imediatas", [])
        if acoes:
            print("  📌 Ações imediatas:")
            for a in acoes:
                print(f"     • {a}")

    print()


def imprimir_top(quantidade: int = 10):
    """Imprime os top N vídeos."""
    _garantir_tabelas()

    with banco.get_conn() as conn:
        rows = conn.execute("""
            SELECT c.titulo, c.tipo, c.duracao_s,
                   m.views, m.likes, m.retencao_pct,
                   m.inscritos_ganhos, c.postado_em
            FROM cortes c
            JOIN metricas m ON m.corte_id = c.id
            ORDER BY m.views DESC
            LIMIT ?
        """, (int(quantidade),)).fetchall()

    if not rows:
        print("  Nenhuma métrica disponível ainda.")
        return

    print(f"\n🏆 TOP {quantidade} VÍDEOS\n")
    print(f"  {'#':>2}  {'Views':>8}  {'Likes':>6}  {'Ret%':>5}  {'Dur':>4}  Título")
    print("  " + "─"*65)
    for i, r in enumerate(rows, 1):
        titulo = (r["titulo"] or "—")[:32]
        dur    = f"{r['duracao_s']:.0f}s" if r["duracao_s"] else "—"
        print(
            f"  {i:>2}  {r['views']:>8,}  {r['likes']:>6,}  "
            f"{r['retencao_pct']:>5.1f}%  {dur:>4}  {titulo}"
        )
    print()


def imprimir_recomendacoes():
    """Imprime apenas as recomendações da última análise."""
    rec = obter_ultima_recomendacao()
    if not rec:
        print("\n  Nenhuma análise disponível. Rode: python analytics.py --analisar\n")
        return

    d = rec["dados"]
    print("\n" + "═"*60)
    print("  RECOMENDAÇÕES DA IA")
    print(f"  Gerado em: {rec['gerado_em']}")
    print("═"*60)
    print(f"\n  {d.get('resumo','')}\n")

    melhor = d.get("melhor_formato", {})
    if melhor:
        print(f"  ✅ Aposte em: {melhor.get('tipo','').upper()}")
        print(f"     {melhor.get('motivo','')}\n")

    temas = d.get("temas_recomendados", [])
    if temas:
        print("  🎯 Temas para priorizar:")
        for t in temas: print(f"     • {t}")
        print()

    evitar = d.get("temas_evitar", [])
    if evitar:
        print("  ⛔ Temas para evitar:")
        for t in evitar: print(f"     • {t}")
        print()

    gancho = d.get("padroes_gancho", {})
    if gancho:
        print(f"  🎣 Gancho que funciona : {gancho.get('funciona','—')}")
        print(f"  ❌ Gancho para evitar  : {gancho.get('evitar','—')}\n")

    horario = d.get("melhor_horario", {})
    dur     = d.get("duracao_ideal", {})
    if horario:
        print(f"  🕐 Poste às: {horario.get('hora',0):02d}h — {horario.get('motivo','')}")
    if dur:
        print(f"  ⏱  Duração ideal: {dur.get('segundos',60)}s — {dur.get('motivo','')}\n")

    acoes = d.get("acoes_imediatas", [])
    if acoes:
        print("  📌 Faça esta semana:")
        for a in acoes: print(f"     • {a}")

    meta = d.get("meta_proxima_semana", "")
    if meta:
        print(f"\n  🎯 Meta: {meta}\n")


# ── INTEGRAÇÃO COM GERADOR ────────────────────────────────

def obter_config_otimizada() -> dict:
    """
    Retorna configurações otimizadas baseadas na última análise.
    Usado pelo gerador_conteudo.py e run_diario.py.
    """
    rec = obter_ultima_recomendacao()
    if not rec:
        return {}

    d = rec["dados"]
    config = {}

    melhor_formato = d.get("melhor_formato", {}).get("tipo")
    if melhor_formato:
        # Priorizar o melhor formato duplicando-o na distribuição
        formatos_base = ["reflexao", "historia", "versiculo"]
        if melhor_formato in formatos_base:
            config["formatos_priorizados"] = [melhor_formato, melhor_formato] + [
                f for f in formatos_base if f != melhor_formato
            ]

    horario = d.get("melhor_horario", {}).get("hora")
    if horario is not None:
        config["horario_ideal"] = horario

    temas = d.get("temas_recomendados", [])
    if temas:
        config["temas_recomendados"] = temas

    temas_evitar = d.get("temas_evitar", [])
    if temas_evitar:
        config["temas_evitar"] = temas_evitar

    duracao = d.get("duracao_ideal", {}).get("segundos")
    if duracao:
        config["duracao_ideal_s"] = duracao

    gancho_bom = d.get("padroes_gancho", {}).get("funciona")
    if gancho_bom:
        config["padrao_gancho"] = gancho_bom

    return config


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Análise de performance — YouTube Shorts + IA"
    )
    parser.add_argument("--coletar",       action="store_true",
                        help="Coletar métricas do YouTube Analytics")
    parser.add_argument("--analisar",      action="store_true",
                        help="Analisar métricas com IA e gerar recomendações")
    parser.add_argument("--relatorio",     action="store_true",
                        help="Relatório completo de performance")
    parser.add_argument("--top",           type=int, default=10, metavar="N",
                        help="Top N vídeos por views (padrão: 10)")
    parser.add_argument("--recomendacoes", action="store_true",
                        help="Mostrar recomendações da última análise")
    parser.add_argument("--dias",          type=int, default=28,
                        help="Dias de histórico para coletar (padrão: 28)")
    args = parser.parse_args()

    # Tentar promover para o logger estruturado (arquivo + formatação).
    # Em caso de falha, o 'logger' básico do módulo (linha 41) já cobre
    # o funcionamento — apenas perde-se a formatação/roteamento extra.
    try:
        from logger_setup import get_logger
        get_logger(__name__)
    except Exception as e:
        logger.warning("logger_setup indisponível, usando logger básico: %s", e)

    if args.coletar:
        print("\n📊 Coletando métricas do YouTube Analytics...\n")
        resultado = coletar_metricas(dias_atras=args.dias)
        print(f"\n  Coletados: {resultado['coletados']} | "
              f"Sem dados: {resultado['sem_dados']} | "
              f"Erros: {resultado['erros']}")

    elif args.analisar:
        print("\n🤖 Analisando performance com IA...\n")
        # Coletar primeiro se necessário
        coletar_metricas(dias_atras=args.dias)
        rec = analisar_com_ia()
        if rec:
            imprimir_recomendacoes()

    elif args.relatorio:
        imprimir_relatorio()

    elif args.recomendacoes:
        imprimir_recomendacoes()

    elif args.top:
        imprimir_top(args.top)

    else:
        # Padrão: coletar + analisar + relatório
        print("\n📊 Pipeline completo de análise\n" + "─"*45)
        print("  1/3 Coletando métricas...")
        coletar_metricas(dias_atras=args.dias)
        print("\n  2/3 Analisando com IA...")
        analisar_com_ia()
        print("\n  3/3 Gerando relatório...")
        imprimir_relatorio()


if __name__ == "__main__":
    main()