from typing import Protocol
from .models import SceneSpec

class SceneProvider(Protocol):
    def generate(self, spec: SceneSpec) -> str:
        ...
