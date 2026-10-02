"""Resilience Layer — ETAPA 3 (integração JobState, Retry, Circuit, Quota)."""
from .retry_engine import RetryEngine, RetryPolicy, ErrorType
from .circuit_breaker import CircuitBreaker, ProviderCircuitBreaker
from .job_models import JobState
class Resilience:
    def __init__(self, job_manager=None, policy=None):
        self.engine = RetryEngine(policy or RetryPolicy())
        self.breaker = ProviderCircuitBreaker()
        self.job_manager = job_manager
    def handle_error(self, provider, operation, error_type, attempt=1, retry_after=None):
        # Integração com JobManager: faz retry se permitido; pausa se QUOTA; cancela se cancelado
        pass
