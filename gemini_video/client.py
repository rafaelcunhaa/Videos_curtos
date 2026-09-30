import os
from .errors import AuthError, QuotaError, GeminiError

class GeminiClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise AuthError("Gemini credentials not configured.")

    def generate_video(self, prompt: str, duration: float = 6.0) -> dict:
        # Mock/dry-run: não chama API real. Confirma contrato.
        # Quando API oficial confirmada, substituir por SDK real.
        return {"status": "mock", "operation_id": "mock-op-1", "output_path": None}
