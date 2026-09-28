from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.models import MarketSnapshot, Signal, TradeResult, TradeRequest
from app.core.pipeline import TradeHubPipeline
from app.execution.executor import DryRunExecutor, TradeExecutor


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
    """Trading layer for Pocket Option Demo market data."""

    def __init__(
        self,
        pipeline: TradeHubPipeline | None = None,
        executor: TradeExecutor | None = None,
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
        self.candle_history: dict[str, deque[dict[str, float]]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self._candle_timestamps: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        self.sequence = 0

    def ingest(self, snapshot: MarketSnapshot) -> None:
        self.history[snapshot.asset].append(snapshot.price)

        candle = snapshot.features.get("candle")
        if not isinstance(candle, dict):
            return

        required = ("open", "high", "low", "close", "volume", "timestamp")
        if not all(key in candle for key in required):
            return

        try:
            timestamp = float(candle["timestamp"])
            normalized = {
                key: float(candle[key])
                for key in ("open", "high", "low", "close", "volume")
            }
        except (TypeError, ValueError):
            return

        timestamps = self._candle_timestamps[snapshot.asset]
        candles = self.candle_history[snapshot.asset]

        if timestamps and timestamp < timestamps[-1]:
            return

        if timestamps and timestamp == timestamps[-1]:
            candles[-1] = normalized
            return

        timestamps.append(timestamp)
        candles.append(normalized)

    def evaluate(self) -> Signal | None:
        candidates: list[Signal] = []

        for asset, candles in self.candle_history.items():
            if len(candles) < 21:
                continue

            signal = self.pipeline.evaluate(
                asset,
                [candle["close"] for candle in candles],
                candles=list(candles),
            )

            if signal is not None:
                candidates.append(signal)

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda signal: signal.confidence,
        )

    async def open_trade(self, signal: Signal, price: float) -> TradeResult:
        request = TradeRequest(
            asset=signal.asset,
            direction=signal.direction,
            amount=self.amount,
            expiration_seconds=self.expiration_seconds,
        )
        result = await self.executor.execute(request)

        if result.accepted and isinstance(self.executor, DryRunExecutor):
            self.sequence += 1
            result.trade_id = f"DRY-{self.sequence:06d}"
            result.reason = (
                f"simulation; entry={price}; confidence={signal.confidence:.1f}"
            )

        return result

    async def open_virtual_trade(
        self,
        signal: Signal,
        price: float,
    ) -> TradeResult:
        """Backward-compatible alias for the existing Demo runner."""
        return await self.open_trade(signal, price)
