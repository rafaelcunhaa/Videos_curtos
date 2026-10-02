"""
Testes isolados ETAPA 3 — Retry + Backoff + Circuit Breaker
Não chamam APIs pagas; não alteram pipeline existente.
"""

import pytest
import time
from pipeline.retry_engine import RetryPolicy, RetryEngine, ErrorType
from pipeline.circuit_breaker import CircuitBreaker, CircuitState, ProviderCircuitBreaker


class TestRetryPolicy:
    def test_backoff_increases(self):
        p = RetryPolicy(backoff_base=10)
        d1 = p.calculate_delay(1)
        d2 = p.calculate_delay(2)
        d3 = p.calculate_delay(3)
        assert d2 > d1
        assert d3 > d2

    def test_max_attempts_blocks(self):
        p = RetryPolicy(max_attempts=2)
        assert p.should_retry(ErrorType.TIMEOUT, 1) is True
        assert p.should_retry(ErrorType.TIMEOUT, 2) is False

    def test_auth_never_retry(self):
        p = RetryPolicy()
        assert p.should_retry(ErrorType.AUTH, 1) is False

    def test_invalid_input_never_retry(self):
        p = RetryPolicy()
        assert p.should_retry(ErrorType.INVALID_INPUT, 1) is False

    def test_rate_limit_retry(self):
        p = RetryPolicy()
        assert p.should_retry(ErrorType.RATE_LIMIT, 1) is True

    def test_classify_auth(self):
        p = RetryPolicy()
        assert p.classify_error(message="unauthorized token") == ErrorType.AUTH

    def test_classify_rate_limit_status(self):
        p = RetryPolicy()
        assert p.classify_error(status_code=429) == ErrorType.RATE_LIMIT

    def test_classify_server_5xx(self):
        p = RetryPolicy()
        assert p.classify_error(status_code=502) == ErrorType.SERVER_5XX

    def test_retry_engine_delay_positive(self):
        engine = RetryEngine()
        d = engine.get_delay(1)
        assert d > 0


class TestCircuitBreaker:
    def test_closed_allows(self):
        cb = CircuitBreaker()
        assert cb.allow_request() is True
        assert cb.get_state() == CircuitState.CLOSED

    def test_opens_after_failures(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED  # ainda 1 falha
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_open_blocks(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.allow_request() is False

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0)
        cb.record_failure()
        # Com cooldown 0, pode ir direto para half-open se já passou
        time.sleep(0.01)
        assert cb.allow_request() is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0)
        cb.record_failure()
        time.sleep(0.01)
        assert cb.allow_request() is True  # half open
        cb.record_success()
        assert cb.get_state() == CircuitState.CLOSED

    def test_half_open_failure_opens(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.5)
        cb.record_failure()
        time.sleep(0.06)
        assert cb.allow_request() is True
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_provider_manager(self):
        pm = ProviderCircuitBreaker()
        assert pm.allow("pexels") is True
        pm.report("pexels", False)
        pm.report("pexels", False)
        pm.report("pexels", False)
        assert pm.allow("pexels") is False
        pm.get_breaker("pexels").record_success()
        assert pm.allow("pexels") is True


class TestRegressionETAPA3:
    def test_pipeline_not_broken(self):
        from gerador_conteudo import gerar_video  # só importa, não executa
        assert callable(gerar_video)
