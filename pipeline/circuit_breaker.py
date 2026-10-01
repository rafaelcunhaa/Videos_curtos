"""
Circuit Breaker — ETAPA 3

Provedor externo → falha → falha → CIRCUIT OPEN
Enquanto aberto: não faz requests inúteis
Depois: HALF_OPEN → tentativa controlada
Sucesso: CLOSED  |  Falha: OPEN
"""

import time
from enum import Enum
from typing import Optional, Callable


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Funcionando normalmente
    OPEN = "OPEN"          # Bloqueado (não faz requests)
    HALF_OPEN = "HALF_OPEN"  # Teste controlado após pausa


class CircuitBreaker:
    """
    Circuit breaker para APIs externas.

    Regras:
    - Falha 3 vezes consecutivas → OPEN
    - Quando OPEN, bloqueia por cooldown_seconds
    - Após cooldown: HALF_OPEN (uma tentativa)
    - Se tentativa HALF_OPEN falhar → OPEN novamente
    - Se sucesso → CLOSED
    """

    DEFAULT_FAILURE_THRESHOLD = 3
    DEFAULT_COOLDOWN = 60  # segundos (pode ser configurado)

    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_seconds: int = DEFAULT_COOLDOWN,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.name = name
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time: float = 0.0
        self.half_open_attempted = False

    def allow_request(self) -> bool:
        """Verifica se pode fazer request."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Verifica se já passou o cooldown
            if time.time() - self.last_failure_time >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempted = False
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Permite apenas uma tentativa; se já tentou, bloqueia
            if not self.half_open_attempted:
                self.half_open_attempted = True
                return True
            return False

        return False

    def record_success(self) -> None:
        """Registra sucesso (fecha circuito)."""
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.half_open_attempted = False
        self.last_failure_time = 0.0

    def record_failure(self) -> None:
        """Registra falha."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Falha na tentativa controlada → volta para OPEN
            self.state = CircuitState.OPEN
            self.half_open_attempted = False
        elif self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def get_state(self) -> CircuitState:
        # Auto-transição OPEN → HALF_OPEN se cooldown passou
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempted = False
        return self.state

    def reset(self) -> None:
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = 0.0
        self.half_open_attempted = False


class ProviderCircuitBreaker:
    """
    Gerenciador de circuit breakers por provider.
    """

    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(self, provider: str, **kwargs) -> CircuitBreaker:
        if provider not in self.breakers:
            self.breakers[provider] = CircuitBreaker(name=provider, **kwargs)
        return self.breakers[provider]

    def allow(self, provider: str) -> bool:
        breaker = self.get_breaker(provider)
        return breaker.allow_request()

    def report(self, provider: str, success: bool) -> None:
        breaker = self.get_breaker(provider)
        if success:
            breaker.record_success()
        else:
            breaker.record_failure()
