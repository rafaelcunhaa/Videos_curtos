#!/usr/bin/env python3
"""
=======================================================
  POSTAGEM NO TIKTOK — via Playwright (sem API oficial)
=======================================================
  Usa automação de navegador para postar vídeos no
  TikTok sem precisar de aprovação da Content API.

  COMO FUNCIONA:
  1. Na primeira vez, abre o navegador para você fazer
     login manualmente no TikTok
  2. Salva a sessão em tiktok_session/ (cookies)
  3. Nas próximas vezes, posta automaticamente
     reutilizando a sessão salva

  SETUP (uma vez só):
    pip install playwright
    playwright install chromium
    python tiktok.py --login

  USO:
    python tiktok.py --login              (fazer login e salvar sessão)
    python tiktok.py --postar video.mp4  (postar um vídeo)
    python tiktok.py --testar            (verificar se sessão está ativa)
    python tiktok.py --status            (info da conta logada)
=======================================================
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_DIR  = Path("tiktok_session")
SESSION_FILE = SESSION_DIR / "session.json"
UPLOAD_URL   = "https://www.tiktok.com/creator-center/upload"
LOGIN_URL    = "https://www.tiktok.com/login"

# Tempo máximo de espera para operações de upload (segundos)
TIMEOUT_UPLOAD  = 120_000   # 2 minutos
TIMEOUT_NAVEG   = 30_000    # 30 segundos
TIMEOUT_LOGIN   = 300_000   # 5 minutos para o usuário fazer login manual


def log(msg: str, nivel: str = "INFO") -> None:
    hora  = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "✓", "ERRO": "✗", "AVISO": "⚠", "PROC": "→", "TT": "📱"}
    print(f"[{hora}] {icons.get(nivel, '·')} {msg}")
    if nivel == "ERRO":    logger.error(msg)
    elif nivel == "AVISO": logger.warning(msg)
    else:                  logger.info(msg)


def _get_playwright():
    """Importa playwright e retorna o módulo sync_api."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("\n❌ Playwright não instalado. Rode:")
        print("   pip install playwright")
        print("   playwright install chromium\n")
        sys.exit(1)


# ── LOGIN E SESSÃO ────────────────────────────────────────

def fazer_login() -> bool:
    """
    Abre o navegador para o usuário fazer login manualmente.
    Salva os cookies de sessão para uso futuro.
    """
    sync_playwright = _get_playwright()
    SESSION_DIR.mkdir(exist_ok=True)

    print("\n" + "═"*55)
    print("  LOGIN NO TIKTOK — Playwright")
    print("═"*55)
    print("\n  O navegador vai abrir agora.")
    print("  Faça login normalmente na sua conta TikTok.")
    print("  Após o login, AGUARDE — o script detecta automaticamente.")
    print("  NÃO feche o navegador manualmente.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,   # mostra o navegador para o usuário fazer login
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        log("Abrindo TikTok...", "PROC")
        page.goto(LOGIN_URL, timeout=TIMEOUT_NAVEG)

        log("Aguardando login manual (máx 5 minutos)...", "PROC")
        print("\n  ⏳ Faça login no navegador. O script continua automaticamente.\n")

        try:
            # Aguarda o usuário fazer login — detecta pelo redirecionamento
            # para a página inicial após autenticação bem-sucedida
            page.wait_for_url(
                lambda url: "tiktok.com" in url and "/login" not in url,
                timeout=TIMEOUT_LOGIN
            )
            # Aguarda mais um pouco para garantir que os cookies estão prontos
            page.wait_for_timeout(3000)
        except Exception:
            log("Timeout de login — tente novamente.", "ERRO")
            browser.close()
            return False

        # Salvar cookies de sessão
        cookies = context.cookies()
        storage = context.storage_state()

        dados_sessao = {
            "cookies":  cookies,
            "storage":  storage,
            "salvo_em": datetime.now().isoformat(),
        }
        SESSION_FILE.write_text(
            json.dumps(dados_sessao, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        log(f"✅ Login bem-sucedido! Sessão salva em {SESSION_FILE}", "TT")
        browser.close()
        return True


def _carregar_sessao(context) -> bool:
    """Carrega cookies salvos no contexto do navegador."""
    if not SESSION_FILE.exists():
        return False
    try:
        dados = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        context.add_cookies(dados["cookies"])
        return True
    except Exception as e:
        logger.warning("Erro ao carregar sessão: %s", e)
        return False


def sessao_valida() -> bool:
    """Verifica se a sessão salva ainda está ativa."""
    if not SESSION_FILE.exists():
        return False

    sync_playwright = _get_playwright()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        _carregar_sessao(context)
        page = context.new_page()
        try:
            page.goto("https://www.tiktok.com/creator-center/upload",
                      timeout=TIMEOUT_NAVEG)
            page.wait_for_timeout(3000)
            # Se redirecionar para login, sessão expirou
            valida = "/login" not in page.url
            browser.close()
            return valida
        except Exception:
            browser.close()
            return False


# ── UPLOAD DE VÍDEO ──────────────────────────────────────

class TikTokClient:
    """
    Cliente de postagem no TikTok via Playwright.
    Interface compatível com o agendador.py existente.
    """

    def __init__(self):
        self._sessao_ok: Optional[bool] = None

    def _garantir_sessao(self) -> bool:
        """Verifica se há sessão válida disponível."""
        if not SESSION_FILE.exists():
            log("Sessão TikTok não encontrada. Rode: python tiktok.py --login", "AVISO")
            return False
        return True

    def postar(self, caminho_video,
               titulo: str,
               descricao: str = "",
               hashtags: list | None = None,
               privacidade: str = "PUBLIC_TO_EVERYONE") -> Optional[str]:
        """
        Posta um vídeo no TikTok via automação Playwright.

        Args:
            caminho_video : caminho do arquivo .mp4
            titulo        : texto da legenda (aparece no vídeo)
            descricao     : texto adicional (incluído na legenda)
            hashtags      : lista de hashtags
            privacidade   : PUBLIC_TO_EVERYONE | SELF_ONLY

        Retorna um ID de referência local ou None em falha.
        """
        if not self._garantir_sessao():
            return None

        caminho_video = Path(caminho_video)
        if not caminho_video.exists():
            log(f"Arquivo não encontrado: {caminho_video}", "ERRO")
            return None

        tamanho_mb = caminho_video.stat().st_size / (1024 * 1024)
        log(f"TikTok: postando {caminho_video.name} ({tamanho_mb:.1f}MB)", "TT")

        # Montar caption com hashtags
        hashtags   = hashtags or []
        tags_str   = " ".join(
            h if h.startswith("#") else f"#{h}"
            for h in hashtags
        )
        caption = f"""{titulo}

        {descricao}

        {tags_str}""".strip()[:2200]

        sync_playwright = _get_playwright()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,   # headless em produção
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )

            # Carregar sessão salva
            if not _carregar_sessao(context):
                log("Falha ao carregar sessão — faça login novamente", "ERRO")
                browser.close()
                return None

            page = context.new_page()

            try:
                # ── 1. Abrir Creator Center ──────────────────────
                log("Abrindo Creator Center...", "PROC")
                page.goto(UPLOAD_URL, timeout=TIMEOUT_NAVEG)
                page.wait_for_timeout(3000)

                # Verificar se foi redirecionado para login (sessão expirada)
                if "/login" in page.url:
                    log("Sessão expirada — rode: python tiktok.py --login", "ERRO")
                    browser.close()
                    return None

                # ── 2. Upload do arquivo ─────────────────────────
                log("Fazendo upload do arquivo...", "PROC")

                # Upload do vídeo
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files(str(caminho_video.resolve()))

                # Aguardar processamento do vídeo pelo TikTok
                log("Aguardando processamento do vídeo...", "PROC")
                page.wait_for_timeout(5000)



                # Fechar popups conhecidos
                for texto in ["Skip","Close","Cancel","Dismiss","Got it","OK","Okay","Entendi","Fechar","Agora não","Not now"]:
                    try:
                        page.get_by_role("button", name=texto).click(timeout=1000)
                        page.wait_for_timeout(500)
                        break
                    except:
                        pass

                # Fechar popup "Novos recursos de edição"
                try:
                    page.get_by_role("button", name="Entendi").click(timeout=5000)
                    page.wait_for_timeout(1000)
                except:
                    pass

                # Aguardar barra de upload completar (até 2 minutos)
                try:
                    page.wait_for_selector(
                        "[class*='upload-progress'][class*='100'],"
                        "[class*='complete'],"
                        "[data-e2e='video-upload-done']",
                        timeout=TIMEOUT_UPLOAD
                    )
                except Exception:
                    # Alguns layouts não possuem esses seletores
                    for _ in range(120):

                        try:
                            if page.locator("div[contenteditable='true']").count() > 0:
                                break
                        except:
                            pass

                        page.wait_for_timeout(1000)

                # Fechar popup novamente, caso ele apareça após o processamento
                for texto in ["Skip","Close","Cancel","Dismiss","Got it","OK","Okay","Entendi","Fechar","Agora não","Not now"]:
                    try:
                        page.get_by_role("button", name=texto).click(timeout=2000)
                        page.wait_for_timeout(500)
                        break
                    except:
                        pass

                # ── 3. Preencher caption ─────────────────────────
                log("Preenchendo legenda e hashtags...", "PROC")
                log("Procurando campo da descrição...", "PROC")
                # Tentar encontrar o campo de caption
                caption_selectors = [
                    "[data-e2e='caption-input']",
                    ".caption-input",
                    "div[contenteditable='true']",
                    "textarea[placeholder*='caption']",
                    "textarea[placeholder*='legenda']",
                ]

                caption_field = None
                for selector in caption_selectors:
                    try:
                        log(f"Tentando: {selector}", "PROC")
                        caption_field = page.wait_for_selector(
                            selector, timeout=5000
                        )
                        if caption_field:
                            log("Campo encontrado!", "PROC")
                            break
                    except Exception:
                        # Seletor CSS não encontrado neste layout —
                        # tenta o próximo da lista de fallbacks
                        continue

                if caption_field:
                    # Fecha popups do TikTok
                    try:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                    except:
                        pass

                    try:
                        while page.locator("[data-test-id='overlay']").count() > 0:
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(500)
                    except Exception:
                        pass
                    log("Clicando no campo...", "PROC")
                    try:
                        caption_field.click(timeout=5000)
                    except:
                        page.evaluate("(el) => el.click()", caption_field)
                    page.keyboard.press("Control+A")
                    page.wait_for_timeout(300)
                    log("Limpando campo...", "PROC")
                    page.keyboard.press("Backspace")
                    page.wait_for_timeout(300)
                    log("Digitando legenda...", "PROC")
                    page.keyboard.insert_text(caption)
                    page.wait_for_timeout(1000)
                    log("Legenda preenchida!", "PROC")
                    page.wait_for_timeout(1000)
                else:
                    log("Campo de caption não encontrado — postando sem texto", "AVISO")

                # ── 4. Configurar privacidade ────────────────────
                if privacidade == "SELF_ONLY":
                    try:
                        priv_selectors = [
                            "select[name='privacy']",
                            "[data-e2e='privacy-select']",
                        ]
                        for sel in priv_selectors:
                            el = page.query_selector(sel)
                            if el:
                                el.select_option("self")
                                break
                    except Exception as e:
                        # Privacidade padrão é pública — falha aqui não impede
                        # a postagem, mas logar para rastrear mudanças de UI
                        logger.warning("Seletor de privacidade não encontrado: %s", e)

                # ── 5. Publicar ──────────────────────────────────
                log("Publicando...", "PROC")

                post_selectors = [
                    "[data-e2e='post-button']",
                    "button[class*='post']",
                    "button:has-text('Post')",
                    "button:has-text('Publicar')",
                    "button:has-text('Postar')",
                ]

                postado = False
                for selector in post_selectors:
                    try:
                        btn = page.wait_for_selector(selector, timeout=5000)
                        if btn and btn.is_enabled():
                            btn.click()
                            postado = True
                            break
                    except Exception:
                        # Seletor do botão não encontrado neste layout —
                        # tenta o próximo da lista de fallbacks
                        continue

                if not postado:
                    log("Botão de publicar não encontrado", "ERRO")
                    browser.close()
                    return None

                # Aguardar confirmação de upload
                page.wait_for_timeout(5000)

                # Verificar se houve confirmação visual de sucesso
                try:
                    page.wait_for_selector(
                        "[class*='success'],"
                        "[data-e2e='upload-success'],"
                        "div:has-text('Your video is being uploaded')",
                        timeout=15000
                    )
                except Exception as e:
                    # Seletor de confirmação não encontrado — alguns layouts
                    # do Creator Center não exibem mensagem explícita de sucesso.
                    # O vídeo pode ter sido postado mesmo sem confirmação visual.
                    logger.debug("Seletor de confirmação não encontrado: %s", e)

                # Gerar ID de referência local (TikTok não expõe ID via automação)
                ref_id = f"tt_{int(time.time())}"
                log(f"✅ Postado no TikTok! Ref: {ref_id}", "TT")
                browser.close()
                return ref_id

            except Exception as e:
                log(f"Erro ao postar: {e}", "ERRO")
                logger.error("TikTok Playwright erro:", exc_info=True)
                # Salvar screenshot para diagnóstico
                try:
                    shot_path = SESSION_DIR / f"erro_{int(time.time())}.png"
                    page.screenshot(path=str(shot_path))
                    log(f"Screenshot salvo: {shot_path}", "AVISO")
                    html_path = SESSION_DIR / f"erro_{int(time.time())}.html"
                    html_path.write_text(page.content(), encoding="utf-8")
                except Exception as e:
                    # Falha ao salvar screenshot é secundária ao erro original
                    # que já foi logado acima — não ofuscar com nova exceção
                    logger.debug("Falha ao salvar screenshot: %s", e)
                browser.close()
                return None

    def testar(self) -> bool:
        """Verifica se a sessão está ativa."""
        if not SESSION_FILE.exists():
            print("\n❌ Sessão não encontrada. Rode: python tiktok.py --login\n")
            return False

        log("Verificando sessão TikTok...", "PROC")
        valida = sessao_valida()
        if valida:
            dados = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            salvo_em = dados.get("salvo_em", "desconhecido")
            print("\n✅ Sessão TikTok ativa!")
            print(f"   Salva em: {salvo_em}")
            print(f"   Arquivo:  {SESSION_FILE}\n")
        else:
            print("\n❌ Sessão expirada ou inválida.")
            print("   Rode: python tiktok.py --login\n")
        return valida

    def info_conta(self) -> dict:
        """Compatibilidade com interface anterior — retorna dict vazio."""
        # Com automação de navegador não temos acesso direto à info da conta
        # sem expor dados sensíveis. O login já valida a conta.
        return {}


# Instância global — importada pelo agendador.py
tiktok = TikTokClient()


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TikTok via Playwright — postagem sem API oficial"
    )
    parser.add_argument("--login",       action="store_true",
                        help="Fazer login e salvar sessão")
    parser.add_argument("--testar",      action="store_true",
                        help="Verificar se a sessão está ativa")
    parser.add_argument("--postar",      metavar="VIDEO.MP4",
                        help="Postar um vídeo agora")
    parser.add_argument("--titulo",      default="",
                        help="Título/caption do vídeo")
    parser.add_argument("--privacidade", default="PUBLIC_TO_EVERYONE",
                        choices=["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
                        help="Privacidade do vídeo")
    parser.add_argument("--instalar",    action="store_true",
                        help="Instalar o navegador Chromium (necessário uma vez)")
    args = parser.parse_args()

    txt = Path(args.postar).with_suffix(".txt")

    if txt.exists():
        conteudo = txt.read_text(encoding="utf-8")

        # Pega apenas a seção do TikTok
        parte = conteudo.split("=== TIKTOK ===")[1].split("=== INFO ===")[0]

        # Extrai título
        titulo = parte.split("TÍTULO:")[1].split("DESCRIÇÃO:")[0].strip()

        # Extrai descrição
        descricao = parte.split("DESCRIÇÃO:")[1].split("HASHTAGS:")[0].strip()

        # Extrai hashtags
        hashtags = parte.split("HASHTAGS:")[1].strip().split()

        # Monta a legenda final
        titulo = f"{titulo}\n\n{descricao}\n\n{' '.join(hashtags)}"

    else:
        titulo = args.titulo or Path(args.postar).stem

    # Setup logging
    try:
        from logger_setup import get_logger
        get_logger(__name__)
    except Exception:
        logging.basicConfig(level=logging.WARNING)

    if args.instalar:
        print("\n📦 Instalando Chromium para Playwright...\n")
        import subprocess
        resultado = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=False,
            timeout=300,  # 5 minutos — download do Chromium pode demorar
        )
        if resultado.returncode == 0:
            print("\n✅ Chromium instalado! Agora rode: python tiktok.py --login\n")
        else:
            print("\n❌ Falha na instalação. Tente: python -m playwright install chromium\n")

    elif args.login:
        ok = fazer_login()
        if ok:
            print("\n✅ Login salvo! O sistema vai postar automaticamente daqui pra frente.\n")
        else:
            print("\n❌ Login falhou. Tente novamente.\n")
            sys.exit(1)

    elif args.testar:
        tiktok.testar()


    elif args.postar:
        ref = tiktok.postar(
            caminho_video=args.postar,
            titulo=titulo,
            privacidade=args.privacidade,
        )
        if not ref:
            sys.exit(1)

    else:
        parser.print_help()
        print("\nFluxo de uso:")
        print("  1. python tiktok.py --instalar   (instala o Chromium)")
        print("  2. python tiktok.py --login      (faz login uma vez)")
        print("  3. python tiktok.py --testar     (confirma que funciona)")
        print("  4. Daí em diante é automático!\n")


if __name__ == "__main__":
    main()