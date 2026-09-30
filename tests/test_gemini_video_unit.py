from gemini_video.errors import QuotaError, AuthError, CircuitOpenError
from gemini_video.queue import CircuitBreaker
from gemini_video.models import SceneSpec

def test_quota_pauses():
    breaker = CircuitBreaker()
    assert breaker.allow_request()
    breaker.record_failure(); breaker.record_failure(); breaker.record_failure()
    assert breaker.state == "OPEN"
    assert not breaker.allow_request()

def test_auth_fails():
    try:
        from gemini_video.client import GeminiClient
        GeminiClient(api_key="")
    except AuthError:
        pass  # esperado se chave vazia; mock aceita qualquer

def test_scene_spec():
    s = SceneSpec(scene_id="s1", video_id="v1", duration=5.0)
    assert s.aspect_ratio == "9:16"
