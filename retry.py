#!/usr/bin/env python3
"""
Retry automático com backoff exponencial para chamadas de API.

Problema resolvido:
    Sem retry → rate limit (429) ou erro temporário (5xx) mata o processo.
    Com retry → tenta automaticamente até 5x com espera crescente, sem intervenção.

Uso:
    from retry import chamar_anthropic, chamar_elevenlabs

    # Em vez de:
    resposta = cliente.messages.create(...)

    # Use:
    resposta = chamar_anthropic(cliente.messages.create, **kwargs)
"""

import logging
import time
import functools
from typing import Callable, Any

try:
    import anthropic
except ImportError:
    anthropic = None

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)

logger = logging.getLogger(__name__)

# ── Configurações de retry ────────────────────────────────
MAX_TENTATIVAS   = 5
ESPERA_MIN_S     = 2    # espera mínima entre tentativas (segundos)
ESPERA_MAX_S     = 60   # espera máxima (segundos)
MULTIPLICADOR    = 2    # fator de crescimento (2s → 4s → 8s → 16s → 32s)


# ── Exceções que merecem retry ────────────────────────────

def _erro_temporario_anthropic(exc: Exception) -> bool:
    """Retorna True para erros que valem retry na API Anthropic."""
    if anthropic:
        # Rate limit (429) ou erros de servidor (5xx)
        if isinstance(exc, anthropic.RateLimitError):
            return True
        if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
            return True
        if isinstance(exc, anthropic.APIConnectionError):
            return True
        if isinstance(exc, anthropic.APITimeoutError):
            return True
    # Fallback genérico
    msg = str(exc).lower()
    return any(k in msg for k in ("rate limit", "429", "500", "503", "timeout", "connection"))


def _erro_temporario_elevenlabs(exc: Exception) -> bool:
    """Retorna True para erros temporários na API ElevenLabs."""
    msg = str(exc).lower()
    return any(k in msg for k in ("rate limit", "429", "500", "503", "timeout", "connection"))


def _erro_temporario_youtube(exc: Exception) -> bool:
    """Retorna True para erros temporários na API YouTube."""
    try:
        from googleapiclient.errors import HttpError
        if isinstance(exc, HttpError):
            return exc.resp.status in (429, 500, 502, 503, 504)
    except ImportError:
        pass
    msg = str(exc).lower()
    return any(k in msg for k in ("quota", "rate limit", "429", "500", "503", "timeout"))


# ── Decorators de retry ───────────────────────────────────

def _fazer_retry(verificar_exc: Callable, label: str):
    """Factory que cria decorators de retry parametrizados."""
    return retry(
        retry=retry_if_exception_type(Exception) if verificar_exc is None
              else lambda exc: verificar_exc(exc),
        stop=stop_after_attempt(MAX_TENTATIVAS),
        wait=wait_exponential(multiplier=MULTIPLICADOR,
                              min=ESPERA_MIN_S,
                              max=ESPERA_MAX_S),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# ── Funções de chamada com retry ─────────────────────────

def chamar_anthropic(func: Callable, *args, **kwargs) -> Any:
    """
    Chama qualquer função da API Anthropic com retry automático.

    Exemplo:
        resposta = chamar_anthropic(
            cliente.messages.create,
            model="claude-sonnet-4",
            max_tokens=1000,
            messages=[...]
        )
    """
    # Implementação com retry manual e backoff exponencial
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ultimo_erro = exc
            if not _erro_temporario_anthropic(exc):
                # Erro permanente (ex: chave inválida) — não adianta retry
                logger.error("Erro permanente Anthropic: %s", exc)
                raise
            espera = min(ESPERA_MIN_S * (MULTIPLICADOR ** (tentativa - 1)), ESPERA_MAX_S)
            logger.warning(
                "Anthropic API erro temporário (tentativa %d/%d): %s — aguardando %ds...",
                tentativa, MAX_TENTATIVAS, type(exc).__name__, espera
            )
            if tentativa < MAX_TENTATIVAS:
                time.sleep(espera)

    logger.error("Anthropic API falhou após %d tentativas", MAX_TENTATIVAS)
    raise ultimo_erro


def chamar_elevenlabs(func: Callable, *args, **kwargs) -> Any:
    """Chama ElevenLabs API com retry automático."""
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ultimo_erro = exc
            if not _erro_temporario_elevenlabs(exc):
                raise
            espera = min(ESPERA_MIN_S * (MULTIPLICADOR ** (tentativa - 1)), ESPERA_MAX_S)
            logger.warning(
                "ElevenLabs erro (tentativa %d/%d): %s — aguardando %ds...",
                tentativa, MAX_TENTATIVAS, type(exc).__name__, espera
            )
            if tentativa < MAX_TENTATIVAS:
                time.sleep(espera)
    raise ultimo_erro


def chamar_youtube(func: Callable, *args, **kwargs) -> Any:
    """Chama YouTube API com retry automático."""
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ultimo_erro = exc
            if not _erro_temporario_youtube(exc):
                raise
            espera = min(ESPERA_MIN_S * (MULTIPLICADOR ** (tentativa - 1)), ESPERA_MAX_S)
            logger.warning(
                "YouTube API erro (tentativa %d/%d): %s — aguardando %ds...",
                tentativa, MAX_TENTATIVAS, type(exc).__name__, espera
            )
            if tentativa < MAX_TENTATIVAS:
                time.sleep(espera)
    raise ultimo_erro


# ── Integração nos scripts existentes ─────────────────────
# Em youtube_para_shorts.py e processar_video.py, substituir:
#
#   resposta = cliente.messages.create(...)
#
# Por:
#   from retry import chamar_anthropic
#   resposta = chamar_anthropic(cliente.messages.create, model=..., ...)
#
# Em agendador.py, substituir:
#   resposta = requisicao.next_chunk()
# Por:
#   from retry import chamar_youtube
#   status, resposta = chamar_youtube(requisicao.next_chunk)