"""
Safe Mode — ETAPA 5 (Dry Run + Safe Mode + Feature Flags)

SAFE_MODE=true: permite gerar, validar, preparar — sem publicar
DRY_RUN=true: não publica, não envia notificações externas, não consome APIs desnecessárias
REQUIRE_APPROVAL=true: adiciona etapa REVIEW antes de SCHEDULED
"""

import os
from enum import Enum


class Mode(str, Enum):
    NORMAL = "NORMAL"
    SAFE = "SAFE"
    DRY_RUN = "DRY_RUN"


def get_mode() -> Mode:
    dry = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
    safe = os.getenv("SAFE_MODE", "false").lower() in ("true", "1", "yes")
    if dry:
        return Mode.DRY_RUN
    if safe:
        return Mode.SAFE
    return Mode.NORMAL


def should_publish() -> bool:
    return get_mode() == Mode.NORMAL


def should_send_notification() -> bool:
    return get_mode() == Mode.NORMAL


def require_approval() -> bool:
    return os.getenv("REQUIRE_APPROVAL", "false").lower() in ("true", "1", "yes")
