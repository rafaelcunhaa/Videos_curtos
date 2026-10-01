"""
Retry Engine — ETAPA 3 (Retry + Backoff + Jitter + Quota)

Implementação segura de retry profissional:
- Classificação de erro (AUTH, RATE_LIMIT, QUOTA, TIMEOUT, NETWORK, 5XX, INVALID_INPUT, CONTENT_POLICY, UNKNOWN)
- Max attempts configurável
- Backoff exponencial com jitter
- Próxima tentativa agendada (next_retry_at)
- Nenhum while True: retry()

Integrável com JobManager via fail() / resume().
"""

from datetime import datetime, timedelta
import random
from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    AUTH = "AUTH"
    PERMISSION = "PERMISSION"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    SERVER_5XX = "5XX"
    INVALID_INPUT = "INVALID_INPUT"
    CONTENT_POLICY = "CONTENT_POLICY"
    UNKNOWN = "UNKNOWN"


class RetryPolicy:
    """
    Política de retry configurável.
    """
    # Padrões seguros: poucos attempts, backoff moderado
    DEFAULT_MAX_ATTEMPTS: int = 3
    DEFAULT_BACKOFF_BASE: float = 2.0  # segundos (para testes rápidos) / pode ser 60 para produção
    DEFAULT_MAX_DELAY: float = 3600.0  # 1h máxima entre tentativas
    DEFAULT_JITTER_MAX: float = 10.0

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        max_delay: float = DEFAULT_MAX_DELAY,
        jitter_max: float = DEFAULT_JITTER_MAX,
    ):
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.max_delay = max_delay
        self.jitter_max = jitter_max

    def calculate_delay(self, attempt: int) -> float:
        """
        Calcula delay até próxima tentativa.
        attempt 1 → base * 2^0 = base
        attempt 2 → base * 2^1 = 2*base
        attempt 3 → base * 2^2 = 4*base
        """
        delay = self.backoff_base * (2 ** (attempt - 1))
        delay = min(delay, self.max_delay)
        # Jitter aleatório para evitar thundering herd
        jitter = random.uniform(0, self.jitter_max)
        return delay + jitter

    def get_retry_schedule(self, attempt: int) -> timedelta:
        seconds = self.calculate_delay(attempt)
        return timedelta(seconds=seconds)

    def should_retry(self, error_type: ErrorType, attempt: int) -> bool:
        """
        Decide se deve tentar novamente.

        Regras:
        - AUTH / PERMISSION: NUNCA retry automático
        - INVALID_INPUT: NÃO retry (falha controlada)
        - QUOTA: retry só após pausa prolongada (não automático imediato)
        - RATE_LIMIT: retry com backoff
        - TIMEOUT / NETWORK / 5XX / UNKNOWN: retry limitado
        """
        if attempt >= self.max_attempts:
            return False

        if error_type in (ErrorType.AUTH, ErrorType.PERMISSION, ErrorType.INVALID_INPUT):
            return False

        if error_type == ErrorType.QUOTA:
            # Quota: só retry se já passou tempo suficiente
            # A decisão final é do caller (próximo_retry_at)
            return False  # Falha controlada; não retry automático

        if error_type in (
            ErrorType.RATE_LIMIT,
            ErrorType.TIMEOUT,
            ErrorType.NETWORK,
            ErrorType.SERVER_5XX,
            ErrorType.UNKNOWN,
        ):
            return True

        return True  # Padrão conservador

    def classify_error(self, exception: Exception | None = None, status_code: int | None = None, message: str | None = None) -> ErrorType:
        """Classifica erro em uma das categorias."""
        if message:
            msg_low = message.lower()
            if "auth" in msg_low or "token" in msg_low or "unauthorized" in msg_low:
                return ErrorType.AUTH
            if "permission" in msg_low or "forbidden" in msg_low:
                return ErrorType.PERMISSION
            if "rate" in msg_low or "limit" in msg_low or "too many" in msg_low:
                return ErrorType.RATE_LIMIT
            if "quota" in msg_low or "exceeded" in msg_low:
                return ErrorType.QUOTA
            if "timeout" in msg_low or "timed out" in msg_low:
                return ErrorType.TIMEOUT
            if "network" in msg_low or "connection" in msg_low:
                return ErrorType.NETWORK
            if "invalid" in msg_low or "bad request" in msg_low or "invalid_input" in msg_low:
                return ErrorType.INVALID_INPUT
            if "content" in msg_low or "policy" in msg_low or "safety" in msg_low or "blocked" in msg_low:
                return ErrorType.CONTENT_POLICY

        if status_code:
            if 500 <= status_code < 600:
                return ErrorType.SERVER_5XX
            if status_code == 429:
                return ErrorType.RATE_LIMIT
            if status_code == 401 or status_code == 403:
                return ErrorType.AUTH if status_code == 401 else ErrorType.PERMISSION
            if status_code == 400:
                return ErrorType.INVALID_INPUT

        return ErrorType.UNKNOWN


class RetryEngine:
    """
    Motor de retry integrado com JobManager.

    Uso:
        engine = RetryEngine(policy=RetryPolicy(max_attempts=3))
        error_type = engine.classify_error(exception=exc)
        if engine.should_retry(error_type, retry_count=2):
            delay = engine.get_delay(3)
            # passa delay ao JobManager
    """

    def __init__(self, policy: RetryPolicy | None = None):
        self.policy = policy or RetryPolicy()

    def should_retry(self, error_type: ErrorType, current_attempt: int) -> bool:
        return self.policy.should_retry(error_type, current_attempt)

    def get_delay(self, attempt: int) -> float:
        return self.policy.calculate_delay(attempt)

    def get_retry_time(self, attempt: int) -> datetime:
        return datetime.now() + self.get_delay(attempt)
