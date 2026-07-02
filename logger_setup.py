#!/usr/bin/env python3
"""
Sistema de logs centralizado.
- Console: colorido, nível INFO
- Arquivo: logs/app.log, rotação diária, mantém 30 dias
- Erros críticos: logs/errors.log separado, mantém 90 dias

Uso em qualquer script:
    from logger_setup import get_logger
    logger = get_logger(__name__)
    logger.info("Processando vídeo...")
    logger.error("Falha no upload", exc_info=True)  # inclui traceback
"""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Cores ANSI para terminal
_CORES = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # verde
    "WARNING":  "\033[33m",   # amarelo
    "ERROR":    "\033[31m",   # vermelho
    "CRITICAL": "\033[35m",   # magenta
}
_RESET = "\033[0m"

_ICONS = {
    "DEBUG":    "·",
    "INFO":     "✓",
    "WARNING":  "⚠",
    "ERROR":    "✗",
    "CRITICAL": "💀",
}


class ColorFormatter(logging.Formatter):
    """Formata logs coloridos para o terminal."""

    def format(self, record: logging.LogRecord) -> str:
        cor   = _CORES.get(record.levelname, "")
        icone = _ICONS.get(record.levelname, "·")
        msg   = super().format(record)
        return f"{cor}[{self.formatTime(record, '%H:%M:%S')}] {icone} {record.getMessage()}{_RESET}"


class PlainFormatter(logging.Formatter):
    """Formata logs sem cor para arquivo."""

    def format(self, record: logging.LogRecord) -> str:
        icone = _ICONS.get(record.levelname, "·")
        base  = f"[{self.formatTime(record, '%Y-%m-%d %H:%M:%S')}] {icone} [{record.levelname}] {record.getMessage()}"
        # Incluir traceback se houver exceção
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


_configurado = False


def configurar_logging(pasta_logs: Path = Path("logs"),
                       nivel_console: int = logging.INFO,
                       nivel_arquivo: int = logging.DEBUG) -> None:
    """
    Configura handlers de log globais. Chamar uma vez no início.
    Chamadas subsequentes são ignoradas (idempotente).
    """
    global _configurado
    if _configurado:
        return
    _configurado = True

    pasta_logs.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── Handler 1: Console colorido ───────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(nivel_console)
    console_handler.setFormatter(ColorFormatter())
    root.addHandler(console_handler)

    # ── Handler 2: app.log — rotação diária, 30 dias ──
    app_log = pasta_logs / "app.log"
    file_handler = TimedRotatingFileHandler(
        filename=str(app_log),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(nivel_arquivo)
    file_handler.setFormatter(PlainFormatter())
    root.addHandler(file_handler)

    # ── Handler 3: errors.log — só erros, 90 dias ─────
    errors_log = pasta_logs / "errors.log"
    error_handler = TimedRotatingFileHandler(
        filename=str(errors_log),
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(PlainFormatter())
    root.addHandler(error_handler)

    # Silenciar libs barulhentas
    for lib in ("urllib3", "googleapiclient", "httpx", "httpcore"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Sistema de logs iniciado → %s", pasta_logs.resolve()
    )


def get_logger(nome: str) -> logging.Logger:
    """
    Retorna um logger nomeado para o módulo.
    Configura automaticamente se ainda não foi feito.

    Uso:
        logger = get_logger(__name__)
    """
    from config import cfg
    configurar_logging(pasta_logs=cfg.pasta_logs)
    return logging.getLogger(nome)