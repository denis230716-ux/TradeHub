from abc import ABC, abstractmethod
from app.core.models import MarketSnapshot, Signal


class Strategy(ABC):
    @abstractmethod
    def generate(self, market: MarketSnapshot) -> Signal | None:
        raise NotImplementedError
