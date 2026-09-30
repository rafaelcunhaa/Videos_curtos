class GeminiError(Exception):
    pass

class QuotaError(GeminiError):
    pass

class AuthError(GeminiError):
    pass

class CircuitOpenError(GeminiError):
    pass
