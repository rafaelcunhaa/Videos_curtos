#!/usr/bin/env python3
"""
=======================================================
  POSTAGEM NATIVA NO TIKTOK
=======================================================
  Publica Shorts diretamente no TikTok via API oficial
  (TikTok Content Posting API v2).

  CONFIGURAÇÃO (uma vez só):
  1. Acesse: https://developers.tiktok.com
  2. Crie um app → ative "Content Posting API"
  3. Configure redirect URI: http://localhost:8080/callback
  4. Copie Client Key e Client Secret
  5. Preencha no .env:
       TIKTOK_CLIENT_KEY=aw...
       TIKTOK_CLIENT_SECRET=...
  6. Autentique:
       python tiktok.py --auth
  7. Teste:
       python tiktok.py --testar

  Uso nos outros scripts:
      from tiktok import tiktok
      video_id = tiktok.postar(caminho_video, titulo, descricao, hashtags)

  Comandos:
    python tiktok.py --auth              (autenticar conta)
    python tiktok.py --postar video.mp4  (postar vídeo)
    python tiktok.py --testar            (verificar configuração)
    python tiktok.py --status            (info da conta)
=======================================================
"""

import json
import logging
import os
import re
import sys
import time
import threading
import webbrowser
import argparse
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Endpoints TikTok ─────────────────────────────────────
TIKTOK_AUTH_URL    = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL   = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_UPLOAD_INIT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL  = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_USER_URL    = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_REVOKE_URL  = "https://open.tiktokapis.com/v2/oauth/revoke/"

TOKEN_FILE_TIKTOK  = "token_tiktok.json"
REDIRECT_URI       = "http://localhost:8080/callback"
SCOPES             = "user.info.basic,video.publish,video.upload"

# Limite de tamanho TikTok: 4GB, mas para Shorts < 500MB é ideal
TAMANHO_MAX_MB     = 500


class _CallbackHandler(BaseHTTPRequestHandler):
    """Servidor HTTP local para capturar o callback OAuth."""
    code = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;text-align:center;padding:50px">
                <h2>&#10003; Autenticado com sucesso!</h2>
                <p>Pode fechar esta janela e voltar ao terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass  # Silenciar logs do servidor HTTP


class TikTokClient:
    """
    Cliente para a TikTok Content Posting API v2.
    Gerencia autenticação OAuth2 e upload de vídeos.
    """

    def __init__(self):
        self._client_key:    str = ""
        self._client_secret: str = ""
        self._access_token:  str = ""
        self._refresh_token: str = ""
        self._token_expiry:  float = 0.0
        self._carregado:     bool = False

    def _carregar_config(self) -> bool:
        """Carrega credenciais do .env e token salvo."""
        if self._carregado:
            return bool(self._client_key)

        try:
            from config import cfg
            # Ler do .env via config
            self._client_key    = os.getenv("TIKTOK_CLIENT_KEY", "")
            self._client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")
        except Exception:
            self._client_key    = os.getenv("TIKTOK_CLIENT_KEY", "")
            self._client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

        # Carregar token salvo
        token_path = Path(TOKEN_FILE_TIKTOK)
        if token_path.exists():
            try:
                dados = json.loads(token_path.read_text(encoding="utf-8"))
                self._access_token  = dados.get("access_token", "")
                self._refresh_token = dados.get("refresh_token", "")
                self._token_expiry  = dados.get("expiry", 0.0)
            except Exception as e:
                logger.warning("Erro ao ler token TikTok: %s", e)

        self._carregado = True
        return bool(self._client_key and self._client_secret)

    def _salvar_token(self) -> None:
        """Persiste token em arquivo."""
        dados = {
            "access_token":  self._access_token,
            "refresh_token": self._refresh_token,
            "expiry":        self._token_expiry,
            "salvo_em":      datetime.now().isoformat(),
        }
        Path(TOKEN_FILE_TIKTOK).write_text(
            json.dumps(dados, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _token_valido(self) -> bool:
        """Verifica se o token ainda é válido (com margem de 5 minutos)."""
        if not self._access_token:
            return False
        return time.time() < (self._token_expiry - 300)

    def _renovar_token(self) -> bool:
        """Tenta renovar o token usando o refresh_token."""
        if not self._refresh_token:
            return False

        logger.info("TikTok: renovando token...")
        try:
            with httpx.Client(timeout=30) as client:
                res = client.post(TIKTOK_TOKEN_URL, data={
                    "client_key":    self._client_key,
                    "client_secret": self._client_secret,
                    "grant_type":    "refresh_token",
                    "refresh_token": self._refresh_token,
                })
                if res.status_code == 200:
                    dados = res.json()
                    self._access_token  = dados["access_token"]
                    self._refresh_token = dados.get("refresh_token", self._refresh_token)
                    self._token_expiry  = time.time() + dados.get("expires_in", 86400)
                    self._salvar_token()
                    logger.info("TikTok: token renovado com sucesso")
                    return True
                else:
                    logger.warning("TikTok: falha ao renovar token: %s", res.text[:200])
        except Exception as e:
            logger.warning("TikTok: erro ao renovar token: %s", e)
        return False

    def _garantir_token(self) -> bool:
        """Garante que há um token válido disponível."""
        if not self._carregar_config():
            return False
        if self._token_valido():
            return True
        if self._renovar_token():
            return True
        logger.warning("TikTok: token inválido — rode: python tiktok.py --auth")
        return False

    # ── Autenticação OAuth2 ──────────────────────────────

    def autenticar(self) -> bool:
        """
        Inicia fluxo OAuth2 — abre navegador e captura código.
        Retorna True se autenticado com sucesso.
        """
        if not self._carregar_config():
            print("\n❌ TIKTOK_CLIENT_KEY ou TIKTOK_CLIENT_SECRET não configurados.")
            print("   Preencha no .env e tente novamente.\n")
            return False

        # Gerar URL de autorização
        params = {
            "client_key":     self._client_key,
            "response_type":  "code",
            "scope":          SCOPES,
            "redirect_uri":   REDIRECT_URI,
            "state":          f"tt_{int(time.time())}",
        }
        auth_url = TIKTOK_AUTH_URL + "?" + urlencode(params)

        print(f"\n🔗 Abrindo navegador para autorização do TikTok...")
        print(f"   Se não abrir automaticamente, acesse:")
        print(f"   {auth_url}\n")

        # Iniciar servidor de callback em thread separada
        _CallbackHandler.code = None
        servidor = HTTPServer(("localhost", 8080), _CallbackHandler)
        thread   = threading.Thread(target=servidor.handle_request)
        thread.daemon = True
        thread.start()

        webbrowser.open(auth_url)

        # Aguardar callback (máx 120s)
        print("⏳ Aguardando autorização no navegador (120s)...")
        for _ in range(120):
            if _CallbackHandler.code:
                break
            time.sleep(1)
        else:
            print("❌ Timeout — autorização não foi concedida.")
            return False

        code = _CallbackHandler.code

        # Trocar código por token
        print("🔄 Trocando código por token de acesso...")
        try:
            with httpx.Client(timeout=30) as client:
                res = client.post(TIKTOK_TOKEN_URL, data={
                    "client_key":    self._client_key,
                    "client_secret": self._client_secret,
                    "code":          code,
                    "grant_type":    "authorization_code",
                    "redirect_uri":  REDIRECT_URI,
                })

            if res.status_code != 200:
                print(f"❌ Erro ao obter token: {res.text[:300]}")
                return False

            dados = res.json()
            if "error" in dados:
                print(f"❌ Erro OAuth: {dados.get('error_description', dados['error'])}")
                return False

            self._access_token  = dados["access_token"]
            self._refresh_token = dados.get("refresh_token", "")
            self._token_expiry  = time.time() + dados.get("expires_in", 86400)
            self._salvar_token()

            print("✅ Autenticado com sucesso! Token salvo em token_tiktok.json")
            logger.info("TikTok: autenticação concluída")
            return True

        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
            logger.error("TikTok: erro na autenticação: %s", e, exc_info=True)
            return False

    # ── Upload de vídeo ──────────────────────────────────

    def postar(self, caminho_video,
               titulo: str,
               descricao: str = "",
               hashtags: list | None = None,
               privacidade: str = "PUBLIC_TO_EVERYONE") -> Optional[str]:
        """
        Faz upload e publica um vídeo no TikTok.

        Args:
            caminho_video : caminho do arquivo .mp4
            titulo        : texto da legenda (máx 2200 chars)
            descricao     : texto adicional
            hashtags      : lista de hashtags (ex: ["#fe", "#deus"])
            privacidade   : PUBLIC_TO_EVERYONE | SELF_ONLY | MUTUAL_FOLLOW_FRIENDS

        Retorna o video_id do TikTok ou None em caso de falha.
        """
        if not self._garantir_token():
            logger.error("TikTok: sem token válido para upload")
            return None

        caminho_video = Path(caminho_video)
        if not caminho_video.exists():
            logger.error("TikTok: arquivo não encontrado: %s", caminho_video)
            return None

        tamanho_mb = caminho_video.stat().st_size / (1024 * 1024)
        if tamanho_mb > TAMANHO_MAX_MB:
            logger.warning(
                "TikTok: arquivo grande (%.1fMB) — recomendado < %dMB",
                tamanho_mb, TAMANHO_MAX_MB
            )

        # Montar caption com hashtags
        hashtags = hashtags or []
        hashtags_str = " ".join(
            h if h.startswith("#") else f"#{h}"
            for h in hashtags
        )
        caption = f"{titulo}\n\n{hashtags_str}".strip()[:2200]

        logger.info("TikTok: iniciando upload de %s (%.1fMB)", caminho_video.name, tamanho_mb)
        print(f"\n[TikTok] Postando: {caminho_video.name} ({tamanho_mb:.1f}MB)")

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        }

        # ── Etapa 1: Inicializar upload ──────────────────
        init_body = {
            "post_info": {
                "title":             caption,
                "privacy_level":     privacidade,
                "disable_duet":      False,
                "disable_comment":   False,
                "disable_stitch":    False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source":     "FILE_UPLOAD",
                "video_size": caminho_video.stat().st_size,
                "chunk_size": caminho_video.stat().st_size,
                "total_chunk_count": 1,
            }
        }

        try:
            with httpx.Client(timeout=30) as client:
                res = client.post(
                    TIKTOK_UPLOAD_INIT,
                    headers=headers,
                    json=init_body
                )

            if res.status_code != 200:
                logger.error("TikTok: erro ao inicializar upload: %s", res.text[:300])
                return None

            dados_init = res.json().get("data", {})
            publish_id  = dados_init.get("publish_id")
            upload_url  = dados_init.get("upload_url")

            if not publish_id or not upload_url:
                logger.error("TikTok: resposta de init inválida: %s", res.text[:300])
                return None

            logger.info("TikTok: upload inicializado (publish_id: %s)", publish_id)

        except Exception as e:
            logger.error("TikTok: erro ao inicializar upload: %s", e, exc_info=True)
            return None

        # ── Etapa 2: Enviar o arquivo ────────────────────
        print(f"[TikTok] Enviando vídeo...", end="", flush=True)
        tamanho = caminho_video.stat().st_size

        try:
            with open(caminho_video, "rb") as f:
                conteudo = f.read()

            with httpx.Client(timeout=300) as client:
                res_upload = client.put(
                    upload_url,
                    content=conteudo,
                    headers={
                        "Content-Type":  "video/mp4",
                        "Content-Range": f"bytes 0-{tamanho-1}/{tamanho}",
                        "Content-Length": str(tamanho),
                    }
                )

            if res_upload.status_code not in (200, 201, 206):
                print(" ❌")
                logger.error("TikTok: erro no upload: %d — %s",
                             res_upload.status_code, res_upload.text[:200])
                return None

            print(" ✅")
            logger.info("TikTok: arquivo enviado com sucesso")

        except Exception as e:
            print(" ❌")
            logger.error("TikTok: erro ao enviar arquivo: %s", e, exc_info=True)
            return None

        # ── Etapa 3: Aguardar processamento ─────────────
        print("[TikTok] Aguardando processamento...", end="", flush=True)
        video_id = self._aguardar_publicacao(publish_id, headers)

        if video_id:
            print(f" ✅")
            url = f"https://www.tiktok.com/@{self._obter_username()}/video/{video_id}"
            logger.info("TikTok: publicado! %s", url)
            print(f"[TikTok] ✅ Publicado: {url}")
            return video_id
        else:
            print(" ❌")
            return None

    def _aguardar_publicacao(self, publish_id: str,
                              headers: dict,
                              max_tentativas: int = 30) -> Optional[str]:
        """Aguarda o TikTok processar e retorna o video_id."""
        for i in range(max_tentativas):
            time.sleep(5)
            try:
                with httpx.Client(timeout=30) as client:
                    res = client.post(
                        TIKTOK_STATUS_URL,
                        headers=headers,
                        json={"publish_id": publish_id}
                    )

                if res.status_code != 200:
                    continue

                dados  = res.json().get("data", {})
                status = dados.get("status", "")

                if status == "PUBLISH_COMPLETE":
                    return dados.get("publicaly_available_post_id", [publish_id])[0]
                elif status in ("FAILED", "ERROR"):
                    logger.error("TikTok: publicação falhou: %s", dados)
                    return None
                # PROCESSING_UPLOAD ou PROCESSING_DOWNLOAD → aguardar

            except Exception as e:
                logger.warning("TikTok: erro ao checar status: %s", e)

        logger.error("TikTok: timeout aguardando publicação")
        return None

    def _obter_username(self) -> str:
        """Retorna o username da conta autenticada."""
        try:
            with httpx.Client(timeout=15) as client:
                res = client.get(
                    TIKTOK_USER_URL,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    params={"fields": "display_name,username"}
                )
            if res.status_code == 200:
                return res.json().get("data", {}).get("user", {}).get("username", "")
        except Exception:
            # Falha de rede/parse ao buscar o username: cai no 'return ""'
            # abaixo. Esta chamada só monta a URL de exibição no log após
            # o vídeo já ter sido postado — não há efeito sobre a postagem
            # em si, apenas uma URL de log menos completa.
            pass
        return ""

    # ── Info da conta ────────────────────────────────────

    def info_conta(self) -> dict:
        """Retorna informações da conta TikTok autenticada."""
        if not self._garantir_token():
            return {}
        try:
            with httpx.Client(timeout=15) as client:
                res = client.get(
                    TIKTOK_USER_URL,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    params={"fields": "display_name,username,avatar_url,follower_count"}
                )
            if res.status_code == 200:
                return res.json().get("data", {}).get("user", {})
        except Exception as e:
            logger.warning("TikTok: erro ao obter info: %s", e)
        return {}

    def testar(self) -> bool:
        """Verifica configuração e token."""
        if not self._carregar_config():
            print("\n❌ Credenciais não configuradas. Preencha no .env:")
            print("   TIKTOK_CLIENT_KEY=...")
            print("   TIKTOK_CLIENT_SECRET=...")
            print("\n   Guia: https://developers.tiktok.com/doc/login-kit-web\n")
            return False

        if not self._garantir_token():
            print("\n❌ Sem token válido. Rode: python tiktok.py --auth\n")
            return False

        info = self.info_conta()
        if info:
            print(f"\n✅ TikTok configurado!")
            print(f"   Conta    : @{info.get('username','—')}")
            print(f"   Nome     : {info.get('display_name','—')}")
            print(f"   Seguidores: {info.get('follower_count','—')}\n")
            return True
        else:
            print("\n⚠️  Token válido mas não foi possível buscar info da conta.")
            print("   Pode ser limitação de escopo — tente postar mesmo assim.\n")
            return True


# Instância global
tiktok = TikTokClient()


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TikTok Content Posting API — postagem nativa"
    )
    parser.add_argument("--auth",    action="store_true",
                        help="Autenticar conta TikTok (OAuth2)")
    parser.add_argument("--testar",  action="store_true",
                        help="Verificar configuração e conta")
    parser.add_argument("--status",  action="store_true",
                        help="Info da conta autenticada")
    parser.add_argument("--postar",  metavar="VIDEO.MP4",
                        help="Postar um vídeo agora")
    parser.add_argument("--titulo",  default="",
                        help="Título/caption do vídeo")
    parser.add_argument("--privacidade", default="PUBLIC_TO_EVERYONE",
                        choices=["PUBLIC_TO_EVERYONE","SELF_ONLY","MUTUAL_FOLLOW_FRIENDS"],
                        help="Privacidade do vídeo")
    parser.add_argument("--setup",   action="store_true",
                        help="Mostrar instruções de configuração")
    args = parser.parse_args()

    if args.setup:
        print("""
╔══════════════════════════════════════════════════════════╗
║   CONFIGURAÇÃO TIKTOK API — PASSO A PASSO               ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  1. Acesse: https://developers.tiktok.com                ║
║  2. Faça login com sua conta TikTok                      ║
║  3. Clique em "My Apps" → "Create App"                   ║
║  4. Preencha nome e categoria                            ║
║  5. Em "Products", adicione:                             ║
║     • Login Kit                                          ║
║     • Content Posting API                                ║
║  6. Em "Redirect URI", adicione:                         ║
║     http://localhost:8080/callback                       ║
║  7. Copie Client Key e Client Secret                     ║
║  8. Preencha no .env:                                    ║
║     TIKTOK_CLIENT_KEY=aw...                              ║
║     TIKTOK_CLIENT_SECRET=...                             ║
║  9. Autentique:                                          ║
║     python tiktok.py --auth                              ║
║                                                          ║
║  ⚠️  IMPORTANTE: o app precisa de aprovação da TikTok   ║
║     para postar publicamente. Enquanto em "Sandbox",     ║
║     só você vê os vídeos (útil para testar).             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""")

    elif args.auth:
        tiktok.autenticar()

    elif args.testar:
        tiktok.testar()

    elif args.status:
        info = tiktok.info_conta()
        if info:
            print(f"\n📱 Conta TikTok:")
            for k, v in info.items():
                print(f"   {k}: {v}")
            print()
        else:
            print("❌ Não autenticado. Rode: python tiktok.py --auth")

    elif args.postar:
        video_id = tiktok.postar(
            caminho_video=args.postar,
            titulo=args.titulo or Path(args.postar).stem,
            privacidade=args.privacidade,
        )
        if not video_id:
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()