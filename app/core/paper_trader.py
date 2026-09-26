from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from app.core.models import MarketSnapshot, Signal, TradeResult, TradeRequest
from app.core.pipeline import TradeHubPipeline
from app.execution.executor import DryRunExecutor


@dataclass(slots=True)
class VirtualTrade:
    trade_id: str
    asset: str
    direction: str
    amount: float
    expiration_seconds: int
    opened_at: datetime
    entry_price: float
    confidence: float


class DemoPaperTrader:
    """Paper-trading layer for Pocket Option Demo market data.

    It never sends an order to Pocket Option. It ranks currently valid signals
    and opens at most one virtual position per decision cycle.
    """

    def __init__(
        self,
        pipeline: TradeHubPipeline | None = None,
        executor: DryRunExecutor | None = None,
        amount: float = 100.0,
        expiration_seconds: int = 5,
        history_size: int = 120,
    ):
        self.pipeline = pipeline or TradeHubPipeline()
        self.executor = executor or DryRunExecutor()
        self.amount = float(amount)
        self.expiration_seconds = int(expiration_seconds)
        self.history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self.sequence = 0

    def ingest(self, snapshot: MarketSnapshot) -> None:
        self.history[snapshot.asset].append(snapshot.price)

    def evaluate(self) -> Signal | None:
        candidates: list[Signal] = []
        for asset, prices in self.history.items():
            signal = self.pipeline.evaluate(asset, list(prices))
            if signal is not None:
                candidates.append(signal)
        if not candidates:
            return None
        return max(candidates, key=lambda signal: signal.confidence)

    async def open_virtual_trade(self, signal: Signal, price: float) -> TradeResult:
        self.sequence += 1
        request = TradeRequest(
            asset=signal.asset,
            direction=signal.direction,
            amount=self.amount,
            expiration_seconds=self.expiration_seconds,
        )
        result = await self.executor.execute(request)
        if result.accepted:
            result.trade_id = f"DRY-{self.sequence:06d}"
            result.reason = (
                f"simulation; entry={price}; confidence={signal.confidence:.1f}"
            )
        return result
