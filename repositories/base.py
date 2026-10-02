"""Repository Pattern — base simples. Não ORM, não framework."""
from abc import ABC, abstractmethod

class BaseRepository(ABC):
    @abstractmethod
    def get_by_id(self, id): ...
