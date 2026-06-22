#!/usr/bin/env python3
"""
=======================================================
  AGENDADOR DE POSTAGEM — YouTube Shorts
=======================================================
  Publica Shorts automaticamente no YouTube usando
  a API oficial do Google. Integrado ao banco.py.

  FLUXO:
  1. Você agenda um corte:
       python agendador.py --agendar CORTE_ID "2026-06-25 14:30"
  2. Deixa o daemon rodando em segundo plano:
       python agendador.py --daemon
  3. Na hora certa, ele faz upload automático e
     marca o corte como "postado" no banco.

  CONFIGURAÇÃO INICIAL (uma vez só):
  1. Crie um projeto no Google Cloud Console
  2. Ative a YouTube Data API v3
  3. Crie credenciais OAuth 2.0 (tipo "Desktop App")
  4. Baixe o JSON e salve como credentials.json

  Guia completo: https://developers.google.com/youtube/v3/guides/uploading_a_video

  COMANDOS:
    python agendador.py --agendar CORTE_ID "2026-06-25 14:30"
    python agendador.py --agendar-lote                        (agenda cortes prontos automaticamente)
    python agendador.py --listar                              (mostra fila de agendamentos)
    python agendador.py --postar-agora CORTE_ID               (posta imediatamente)
    python agendador.py --daemon                              (roda em loop verificando a fila)
    python agendador.py --auth                                (autenticar com YouTube)
=======================================================
"""

import os, sys, json, time, argparse, schedule
from pathlib import Path
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════
#  CONFIGURAÇÕES
# ═══════════════════════════════════════════════════════
CREDENTIALS_FILE = "credentials.json"    # baixado do Google Cloud Console
TOKEN_FILE       = "token.json"          # gerado automaticamente após auth

# Horários ideais para postar (hora local) — melhores para engajamento
HORARIOS_IDEAIS  = ["07:00", "12:00", "18:00", "21:00"]

# Intervalo mínimo entre posts (em horas) — evita spam
INTERVALO_HORAS  = 3

# Categoria do YouTube (22 = Pessoas e Blogs, 29 = Sem fins lucrativos)
CATEGORIA_ID     = "22"

# Privacidade padrão ao agendar (public | private | unlisted)
PRIVACIDADE_PADRAO = "public"

# Verificar fila a cada X minutos no daemon
DAEMON_INTERVALO_MIN = 5
# ═══════════════════════════════════════════════════════

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def log(msg, nivel="INFO"):
    hora = datetime.now().strftime("%H:%M:%S")
    p = {"INFO":"✓","ERRO":"✗","AVISO":"⚠","PROC":"→","YT":"📺","DB":"🗄️"}
    print(f"[{hora}] {p.get(nivel,'·')} {msg}")

# ─── AUTENTICAÇÃO GOOGLE ──────────────────────────────────

def autenticar():
    """OAuth2 com YouTube — abre navegador na primeira vez"""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            log("Token renovado automaticamente")
        else:
            if not Path(CREDENTIALS_FILE).exists():
                print(f"\n❌ Arquivo '{CREDENTIALS_FILE}' não encontrado.")
                print("\nSiga estes passos para configurar:")
                print("  1. Acesse: https://console.cloud.google.com")
                print("  2. Crie um projeto (ou selecione um existente)")
                print("  3. Ative a 'YouTube Data API v3'")
                print("  4. Vá em 'Credenciais' → 'Criar credencial' → 'ID do cliente OAuth'")
                print("  5. Tipo: 'App para computador'")
                print("  6. Baixe o JSON e salve como: credentials.json")
                print("  7. Rode: python agendador.py --auth\n")
                sys.exit(1)

            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            log("Autenticação realizada com sucesso! ✅", "YT")

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds

def criar_servico_youtube():
    from googleapiclient.discovery import build
    creds = autenticar()
    return build("youtube", "v3", credentials=creds)

# ─── UPLOAD PARA YOUTUBE ──────────────────────────────────

def fazer_upload(corte):
    """Faz o upload do Short para o YouTube"""
    from googleapiclient.http import MediaFileUpload

    caminho_video = corte.get("caminho_video")
    if not caminho_video or not Path(caminho_video).exists():
        log(f"Arquivo não encontrado: {caminho_video}", "ERRO")
        return None

    # Carregar título e descrição do arquivo .txt se existir
    titulo    = corte.get("titulo_yt") or corte.get("titulo") or "Short"
    descricao = corte.get("descricao") or ""
    hashtags  = []

    caminho_txt = corte.get("caminho_txt")
    if caminho_txt and Path(caminho_txt).exists():
        conteudo = Path(caminho_txt).read_text(encoding="utf-8")
        # Extrair campos do txt
        for linha in conteudo.split("\n"):
            if linha.startswith("TÍTULO:"):
                proximo = True
            elif linha.startswith("DESCRIÇÃO:"):
                proximo = True
            elif linha.startswith("HASHTAGS:"):
                proximo = True

        # Parse simples do txt
        partes = conteudo.split("\n\n")
        for parte in partes:
            if parte.startswith("TÍTULO:"):
                titulo = parte.replace("TÍTULO:", "").strip()
            elif parte.startswith("DESCRIÇÃO:"):
                descricao = parte.replace("DESCRIÇÃO:", "").strip()
            elif parte.startswith("HASHTAGS:"):
                hashtags = parte.replace("HASHTAGS:", "").strip().split()

    # Montar descrição final com hashtags
    if hashtags:
        descricao_final = descricao + "\n\n" + " ".join(hashtags)
    else:
        descricao_final = descricao

    # Tags extraídas das hashtags (sem #)
    tags = [h.lstrip("#") for h in hashtags][:15]  # YouTube aceita até 15 tags

    log(f"Iniciando upload: {titulo[:50]}...", "YT")
    log(f"Arquivo: {Path(caminho_video).name} ({Path(caminho_video).stat().st_size/1024/1024:.1f} MB)", "YT")

    servico = criar_servico_youtube()

    corpo = {
        "snippet": {
            "title":       titulo[:100],       # limite do YouTube
            "description": descricao_final[:5000],
            "tags":        tags,
            "categoryId":  CATEGORIA_ID,
        },
        "status": {
            "privacyStatus":          PRIVACIDADE_PADRAO,
            "selfDeclaredMadeForKids": False,
        }
    }

    midia = MediaFileUpload(
        caminho_video,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024  # 10MB por chunk
    )

    requisicao = servico.videos().insert(
        part="snippet,status",
        body=corpo,
        media_body=midia
    )

    # Upload com progresso
    resposta = None
    while resposta is None:
        status_upload, resposta = requisicao.next_chunk()
        if status_upload:
            pct = int(status_upload.progress() * 100)
            print(f"\r   Enviando... {pct}%", end="", flush=True)

    print()  # nova linha após progresso

    video_id = resposta.get("id")
    url_short = f"https://youtube.com/shorts/{video_id}"
    log(f"✅ Postado com sucesso!", "YT")
    log(f"   URL: {url_short}", "YT")

    return video_id

# ─── AGENDAMENTO ─────────────────────────────────────────

def proximos_horarios(quantidade=10):
    """Calcula os próximos horários de postagem ideais"""
    agora    = datetime.now()
    horarios = []
    dia      = agora

    while len(horarios) < quantidade:
        for h in HORARIOS_IDEAIS:
            hora, minuto = map(int, h.split(":"))
            dt = dia.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            if dt > agora + timedelta(minutes=10):  # pelo menos 10 min no futuro
                horarios.append(dt)
        dia = dia + timedelta(days=1)

    return sorted(horarios)[:quantidade]

def agendar_corte_automatico(corte_id, data_hora_str=None):
    """Agenda um corte — escolhe horário ideal se não especificado"""
    import banco
    banco.inicializar()

    cortes = banco.listar_cortes()
    corte  = next((c for c in cortes if c["id"] == corte_id), None)
    if not corte:
        log(f"Corte {corte_id} não encontrado no banco.", "ERRO")
        return

    if data_hora_str:
        try:
            dt = datetime.strptime(data_hora_str, "%Y-%m-%d %H:%M")
        except ValueError:
            log("Formato de data inválido. Use: 'AAAA-MM-DD HH:MM'", "ERRO")
            return
    else:
        # Encontrar próximo horário ideal disponível
        horarios_ocupados = []
        agendados = banco.listar_cortes(status="agendado")
        for ag in agendados:
            if ag.get("agendado_para"):
                try:
                    horarios_ocupados.append(
                        datetime.strptime(ag["agendado_para"], "%Y-%m-%d %H:%M:%S")
                    )
                except Exception:
                    pass

        dt = None
        for h in proximos_horarios(20):
            # Verificar intervalo mínimo
            conflito = any(abs((h - oc).total_seconds()) < INTERVALO_HORAS * 3600
                          for oc in horarios_ocupados)
            if not conflito:
                dt = h
                break

        if not dt:
            dt = proximos_horarios(1)[0]

    banco.agendar_corte(corte_id, dt.strftime("%Y-%m-%d %H:%M:%S"))
    log(f"Corte {corte_id} agendado para: {dt.strftime('%d/%m/%Y às %H:%M')}", "DB")
    log(f"Título: {corte.get('titulo','—')}")
    return dt

def agendar_lote():
    """Agenda todos os cortes prontos nos próximos horários ideais"""
    import banco
    banco.inicializar()

    prontos = banco.listar_cortes(status="pronto")
    if not prontos:
        log("Nenhum corte com status 'pronto' para agendar.", "AVISO")
        return

    log(f"Agendando {len(prontos)} cortes automaticamente...", "PROC")

    horarios_ocupados = []
    agendados = banco.listar_cortes(status="agendado")
    for ag in agendados:
        if ag.get("agendado_para"):
            try:
                horarios_ocupados.append(
                    datetime.strptime(ag["agendado_para"], "%Y-%m-%d %H:%M:%S")
                )
            except Exception:
                pass

    horarios_disponiveis = []
    for h in proximos_horarios(len(prontos) * 3):
        conflito = any(abs((h - oc).total_seconds()) < INTERVALO_HORAS * 3600
                      for oc in horarios_ocupados + horarios_disponiveis)
        if not conflito:
            horarios_disponiveis.append(h)
        if len(horarios_disponiveis) >= len(prontos):
            break

    print(f"\n{'Corte':<6} {'Título':<35} {'Agendado para':<20}")
    print("─" * 65)

    for corte, dt in zip(prontos, horarios_disponiveis):
        banco.agendar_corte(corte["id"], dt.strftime("%Y-%m-%d %H:%M:%S"))
        titulo_curto = (corte.get("titulo") or "—")[:33]
        print(f"  {corte['id']:<4}  {titulo_curto:<35}  {dt.strftime('%d/%m %H:%M')}")

    print(f"\n✅ {len(prontos)} cortes agendados com intervalo mínimo de {INTERVALO_HORAS}h entre posts.")

def postar_agora(corte_id):
    """Faz upload imediato de um corte"""
    import banco
    banco.inicializar()

    cortes = banco.listar_cortes()
    corte  = next((c for c in cortes if c["id"] == corte_id), None)
    if not corte:
        log(f"Corte {corte_id} não encontrado.", "ERRO")
        return False

    log(f"Postando agora: [{corte_id}] {corte.get('titulo','—')}", "YT")
    yt_id = fazer_upload(corte)

    if yt_id:
        banco.atualizar_status_corte(corte_id, "postado", youtube_short_id=yt_id)
        log(f"Status atualizado para 'postado' no banco.", "DB")
        log(f"https://youtube.com/shorts/{yt_id}", "YT")
        return True
    else:
        log("Upload falhou.", "ERRO")
        return False

def verificar_e_postar_agendados():
    """Verifica a fila e posta os que chegaram na hora"""
    import banco
    banco.inicializar()

    pendentes = banco.cortes_pendentes_agendamento()
    if not pendentes:
        return

    log(f"{len(pendentes)} corte(s) para postar agora!", "YT")
    for corte in pendentes:
        log(f"Postando: [{corte['id']}] {corte.get('titulo','—')}", "YT")
        yt_id = fazer_upload(corte)
        if yt_id:
            banco.atualizar_status_corte(corte["id"], "postado", youtube_short_id=yt_id)
            log(f"✅ Postado: https://youtube.com/shorts/{yt_id}", "YT")
        else:
            log(f"Falha no upload do corte {corte['id']}", "ERRO")
        time.sleep(5)  # pausa entre uploads

def listar_fila():
    """Mostra a fila de agendamentos"""
    import banco
    banco.inicializar()

    prontos   = banco.listar_cortes(status="pronto")
    agendados = banco.listar_cortes(status="agendado")
    postados  = banco.listar_cortes(status="postado")

    print("\n" + "═"*65)
    print("  FILA DE POSTAGEM")
    print("═"*65)

    if agendados:
        print(f"\n📅 AGENDADOS ({len(agendados)}):\n")
        print(f"  {'ID':>4}  {'Data/hora':>16}  {'Dur':>4}  Título")
        print("  " + "─"*58)
        for c in sorted(agendados, key=lambda x: x.get("agendado_para","")):
            agendado = c.get("agendado_para","—")
            try:
                dt = datetime.strptime(agendado, "%Y-%m-%d %H:%M:%S")
                agendado = dt.strftime("%d/%m/%Y %H:%M")
                diff = dt - datetime.now()
                if diff.total_seconds() > 0:
                    horas = int(diff.total_seconds() // 3600)
                    mins  = int((diff.total_seconds() % 3600) // 60)
                    agendado += f" (em {horas}h{mins:02d}m)"
            except Exception:
                pass
            dur = f"{c.get('duracao_s',0):.0f}s"
            print(f"  {c['id']:>4}  {agendado:<35}  {dur:>4}  {(c.get('titulo') or '—')[:25]}")

    if prontos:
        print(f"\n🎥 PRONTOS para agendar ({len(prontos)}):\n")
        print(f"  {'ID':>4}  {'Tipo':>6}  {'Dur':>4}  Título")
        print("  " + "─"*50)
        for c in prontos:
            dur = f"{c.get('duracao_s',0):.0f}s"
            print(f"  {c['id']:>4}  {c.get('tipo','—'):>6}  {dur:>4}  {(c.get('titulo') or '—')[:35]}")

    if postados:
        print(f"\n✅ POSTADOS ({len(postados)}) — últimos 5:\n")
        for c in postados[-5:]:
            yt_id = c.get("youtube_short_id","—")
            print(f"  [{c['id']:>4}] {(c.get('titulo') or '—')[:35]}")
            if yt_id and yt_id != "—":
                print(f"         https://youtube.com/shorts/{yt_id}")

    if not agendados and not prontos and not postados:
        print("\n  Nenhum corte no banco ainda.")
        print("  Rode primeiro: python youtube_para_shorts.py --url URL\n")

    print()

def daemon():
    """Loop que verifica e posta agendados automaticamente"""
    log(f"Daemon iniciado — verificando fila a cada {DAEMON_INTERVALO_MIN} min", "PROC")
    log("Pressione Ctrl+C para parar.\n")

    # Verificar imediatamente ao iniciar
    verificar_e_postar_agendados()

    # Agendar verificação periódica
    schedule.every(DAEMON_INTERVALO_MIN).minutes.do(verificar_e_postar_agendados)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log("Daemon encerrado pelo usuário.")

# ─── CLI ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agendador de postagem — YouTube Shorts"
    )
    parser.add_argument("--auth",           action="store_true",
                        help="Autenticar com conta do YouTube")
    parser.add_argument("--agendar",        metavar="CORTE_ID",
                        help="Agendar um corte (adicione data opcional: '2026-06-25 14:30')")
    parser.add_argument("--data",           metavar="'AAAA-MM-DD HH:MM'",
                        help="Data/hora para o agendamento")
    parser.add_argument("--agendar-lote",   action="store_true",
                        help="Agenda todos os cortes prontos automaticamente")
    parser.add_argument("--listar",         action="store_true",
                        help="Mostra a fila de agendamentos")
    parser.add_argument("--postar-agora",   metavar="CORTE_ID",
                        help="Posta um corte imediatamente")
    parser.add_argument("--daemon",         action="store_true",
                        help="Roda em loop postando agendados automaticamente")
    args = parser.parse_args()

    if args.auth:
        log("Iniciando autenticação com YouTube...", "YT")
        autenticar()
        log("Autenticado! Token salvo em token.json ✅", "YT")

    elif args.agendar:
        agendar_corte_automatico(int(args.agendar), args.data)

    elif args.agendar_lote:
        agendar_lote()

    elif args.listar:
        listar_fila()

    elif args.postar_agora:
        postar_agora(int(args.postar_agora))

    elif args.daemon:
        daemon()

    else:
        print("\n" + "═"*55)
        print("  AGENDADOR DE SHORTS — YouTube")
        print("═"*55)
        parser.print_help()
        print("\nExemplos rápidos:")
        print("  python agendador.py --auth")
        print("  python agendador.py --agendar-lote")
        print("  python agendador.py --listar")
        print("  python agendador.py --agendar 3 --data '2026-06-25 18:00'")
        print("  python agendador.py --postar-agora 1")
        print("  python agendador.py --daemon\n")

if __name__ == "__main__":
    main()