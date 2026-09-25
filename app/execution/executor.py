from abc import ABC, abstractmethod
from app.core.models import TradeRequest, TradeResult


class TradeExecutor(ABC):
    @abstractmethod
    async def execute(self, request: TradeRequest) -> TradeResult:
        raise NotImplementedError


class DryRunExecutor(TradeExecutor):
    async def execute(self, request: TradeRequest) -> TradeResult:
        return TradeResult(
            accepted=True,
            trade_id="DRY_RUN",
            reason="simulation",
        )
