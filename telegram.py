#!/usr/bin/env python3
"""
=======================================================
  NOTIFICAÇÕES TELEGRAM
=======================================================
  Envia notificações automáticas para o seu Telegram
  sobre tudo que acontece no sistema:

  ✅ Short postado com sucesso
  ❌ Erro em qualquer etapa
  ⚠️  Saldo de API baixo
  📊 Resumo diário (vídeos gerados, postados, custo)
  🎬 Pipeline concluído

  CONFIGURAÇÃO (2 minutos):
  1. Abra o Telegram e busque: @BotFather
  2. Digite /newbot e siga as instruções
  3. Copie o token gerado (ex: 7123456789:AAF...)
  4. Busque @userinfobot no Telegram e copie seu Chat ID
  5. Preencha no .env:
       TELEGRAM_BOT_TOKEN=7123456789:AAF...
       TELEGRAM_CHAT_ID=123456789

  Uso em outros scripts:
      from telegram import notificar
      notificar.short_postado("Meu título", "https://youtube.com/shorts/xxx")
      notificar.erro("youtube_para_shorts", "Falha no download", exc)
      notificar.resumo_diario(gerados=3, postados=2, custo_usd=0.12)
=======================================================
"""

import logging
import traceback
from datetime import datetime
from typing import Optional

import httpx
from constantes import TAXA_CAMBIO_USD_BRL, TIMEOUT_TELEGRAM_API

logger = logging.getLogger(__name__)

# ── Emojis por tipo de notificação ───────────────────────
_EMOJI = {
    "sucesso":  "✅",
    "erro":     "❌",
    "aviso":    "⚠️",
    "info":     "ℹ️",
    "resumo":   "📊",
    "pipeline": "🎬",
    "agendado": "📅",
    "dinheiro": "💰",
}

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class _Notificador:
    """
    Cliente de notificações Telegram.
    Falha silenciosamente se não configurado — nunca derruba o pipeline.
    """

    def __init__(self):
        self._token:   str = ""
        self._chat_id: str = ""
        self._ativo:   bool = False

    def _carregar_config(self) -> bool:
        """Carrega configuração do config.py. Retorna True se configurado."""
        if self._ativo:
            return True
        try:
            from config import cfg
            if cfg.telegram_token and cfg.telegram_chat_id:
                self._token   = cfg.telegram_token
                self._chat_id = cfg.telegram_chat_id
                self._ativo   = True
                return True
        except Exception:
            # Falha ao importar config ou ler atributos: cai no 'return False'
            # abaixo, que já é o sinal correto de "Telegram não configurado"
            # esperado por quem chama este método. Não há perda de dado.
            pass
        return False

    def _enviar(self, texto: str, silencioso: bool = False) -> bool:
        """
        Envia mensagem para o Telegram.
        silencioso=True → não toca notificação no celular (para resumos noturnos)
        Retorna True se enviado com sucesso.
        """
        if not self._carregar_config():
            return False  # não configurado — silêncio total

        url  = TELEGRAM_API.format(token=self._token)
        body = {
            "chat_id":              self._chat_id,
            "text":                 texto,
            "parse_mode":           "HTML",
            "disable_notification": silencioso,
        }

        try:
            with httpx.Client(timeout=TIMEOUT_TELEGRAM_API) as client:
                res = client.post(url, json=body)
                if res.status_code == 200:
                    return True
                else:
                    logger.warning(
                        "Telegram: falha ao enviar (status %d): %s",
                        res.status_code, res.text[:200]
                    )
        except httpx.TimeoutException:
            logger.warning("Telegram: timeout ao enviar notificação")
        except Exception as e:
            logger.warning("Telegram: erro inesperado: %s", e)

        return False

    # ── Notificações específicas ──────────────────────────

    def short_postado(self, titulo: str, url_short: str,
                       formato: str = "", duracao_s: float = 0) -> None:
        """Avisa quando um Short for postado com sucesso."""
        dur = f" • {duracao_s:.0f}s" if duracao_s else ""
        fmt = f" • {formato.upper()}" if formato else ""
        texto = (
            f"{_EMOJI['sucesso']} <b>Short postado!</b>\n\n"
            f"📌 {titulo}\n"
            f"🔗 {url_short}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            f"{fmt}{dur}"
        )
        self._enviar(texto)
        logger.info("Telegram: notificação de postagem enviada")

    def erro(self, origem: str, mensagem: str,
             excecao: Optional[Exception] = None) -> None:
        """Avisa quando qualquer erro crítico ocorrer."""
        detalhe = ""
        if excecao:
            tb = traceback.format_exc()
            # Pegar só as últimas 3 linhas do traceback
            linhas = [l for l in tb.strip().split("\n") if l.strip()]
            detalhe = "\n<code>" + "\n".join(linhas[-3:]) + "</code>"

        texto = (
            f"{_EMOJI['erro']} <b>Erro em {origem}</b>\n\n"
            f"💬 {mensagem}"
            f"{detalhe}\n\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        self._enviar(texto)
        logger.info("Telegram: notificação de erro enviada")

    def aviso(self, mensagem: str) -> None:
        """Aviso não crítico."""
        texto = (
            f"{_EMOJI['aviso']} <b>Aviso</b>\n\n"
            f"{mensagem}\n\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        self._enviar(texto)

    def pipeline_concluido(self, origem: str, total: int,
                            sucesso: int, custo_usd: float = 0.0) -> None:
        """Avisa quando um pipeline terminar."""
        icone = _EMOJI["sucesso"] if sucesso == total else _EMOJI["aviso"]
        custo_brl = custo_usd * TAXA_CAMBIO_USD_BRL
        texto = (
            f"{icone} <b>Pipeline concluído: {origem}</b>\n\n"
            f"🎬 Vídeos: {sucesso}/{total} gerados\n"
            f"💰 Custo API: ${custo_usd:.4f} (~R${custo_brl:.2f})\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        self._enviar(texto)

    def resumo_diario(self, gerados: int, postados: int,
                       agendados: int, custo_usd: float) -> None:
        """Resumo diário — enviado silenciosamente para não acordar."""
        custo_brl = custo_usd * TAXA_CAMBIO_USD_BRL
        texto = (
            f"{_EMOJI['resumo']} <b>Resumo do dia</b> — "
            f"{datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"🎬 Vídeos gerados  : {gerados}\n"
            f"📤 Postados hoje   : {postados}\n"
            f"📅 Agendados       : {agendados}\n"
            f"💰 Custo total API : ${custo_usd:.4f} (~R${custo_brl:.2f})"
        )
        self._enviar(texto, silencioso=True)

    def saldo_baixo(self, custo_total_usd: float,
                    limite_usd: float = 5.0) -> None:
        """Avisa quando o gasto acumulado ultrapassar um limite."""
        custo_brl = custo_total_usd * TAXA_CAMBIO_USD_BRL
        texto = (
            f"{_EMOJI['aviso']} <b>Atenção: gasto de API alto</b>\n\n"
            f"💳 Total gasto: ${custo_total_usd:.4f} (~R${custo_brl:.2f})\n"
            f"📌 Limite configurado: ${limite_usd:.2f}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            f"Verifique seu saldo em: console.anthropic.com"
        )
        self._enviar(texto)

    def short_agendado(self, titulo: str, data_hora: str) -> None:
        """Avisa quando um Short for agendado."""
        texto = (
            f"{_EMOJI['agendado']} <b>Short agendado</b>\n\n"
            f"📌 {titulo}\n"
            f"🕐 Postará em: {data_hora}"
        )
        self._enviar(texto, silencioso=True)

    def testar(self) -> bool:
        """Envia mensagem de teste. Retorna True se funcionou."""
        texto = (
            f"✅ <b>Bot configurado com sucesso!</b>\n\n"
            f"Seu sistema de notificações está funcionando.\n"
            f"Você receberá avisos aqui quando:\n\n"
            f"• Um Short for postado\n"
            f"• Ocorrer algum erro\n"
            f"• O pipeline diário terminar\n"
            f"• O gasto de API estiver alto\n\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        ok = self._enviar(texto)
        if ok:
            print("✅ Mensagem de teste enviada! Verifique seu Telegram.")
        else:
            print("❌ Falhou. Verifique TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env")
        return ok


# Instância global — importada pelos outros scripts
notificar = _Notificador()


# ── CLI para testar ───────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Notificações Telegram")
    parser.add_argument("--testar",  action="store_true", help="Envia mensagem de teste")
    parser.add_argument("--setup",   action="store_true", help="Mostra instruções de configuração")
    args = parser.parse_args()

    if args.testar:
        notificar.testar()

    elif args.setup:
        print("""
╔══════════════════════════════════════════════════════╗
║   CONFIGURAÇÃO DO BOT TELEGRAM — 2 MINUTOS           ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  1. Abra o Telegram e busque: @BotFather             ║
║  2. Digite: /newbot                                  ║
║  3. Dê um nome ao bot (ex: Meu Canal Bot)            ║
║  4. Dê um username (ex: meucanal_bot)                ║
║  5. Copie o TOKEN que o BotFather enviar             ║
║                                                      ║
║  6. Busque @userinfobot no Telegram                  ║
║  7. Digite qualquer coisa — ele retorna seu Chat ID  ║
║                                                      ║
║  8. Preencha no arquivo .env:                        ║
║     TELEGRAM_BOT_TOKEN=seu_token_aqui                ║
║     TELEGRAM_CHAT_ID=seu_chat_id_aqui                ║
║                                                      ║
║  9. Teste:                                           ║
║     python telegram.py --testar                      ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
""")
    else:
        parser.print_help()