from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any

from app.core.models import MarketSnapshot, Signal, TradeResult, TradeRequest
from app.core.pipeline import TradeHubPipeline
from app.execution.executor import DryRunExecutor, TradeExecutor
from app.external_signals.pocket_signals import ExternalSignalSynchronizer


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
        amount: float = 1.0,
        expiration_seconds: int = 5,
        starting_balance: float = 921.15,
        base_risk_percent: float = 0.5,
        strong_risk_percent: float = 0.75,
        max_risk_percent: float = 1.0,
        history_size: int = 120,
        cooldown_seconds: int = 5,
        external_synchronizer: ExternalSignalSynchronizer | None = None,
    ):
        self.pipeline = pipeline or TradeHubPipeline()
        self.executor = executor or DryRunExecutor()
        self.amount = float(amount)
        self.starting_balance = max(1.0, float(starting_balance))
        self.base_risk_percent = max(0.0, float(base_risk_percent))
        self.strong_risk_percent = max(self.base_risk_percent, float(strong_risk_percent))
        self.max_risk_percent = max(self.strong_risk_percent, float(max_risk_percent))
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
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self._cooldown_until: dict[str, float] = {}
        # Block repeated entries caused by multiple websocket updates of one candle.
        self._last_trade_candle: dict[str, float] = {}
        self.external_synchronizer = external_synchronizer

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
            current = candles[-1]
            current["high"] = max(current["high"], normalized["high"])
            current["low"] = min(current["low"], normalized["low"])
            current["close"] = normalized["close"]
            current["volume"] += normalized["volume"]
            return

        timestamps.append(timestamp)
        candles.append(normalized)

    def evaluate(self) -> Signal | None:
        return self.evaluate_with_diagnostics()[0]

    def evaluate_with_diagnostics(
        self,
    ) -> tuple[Signal | None, dict[str, dict[str, float | str | bool]]]:
        candidates: list[Signal] = []
        diagnostics: dict[str, dict[str, float | str | bool]] = {}

        for asset, candles in self.candle_history.items():
            if len(candles) < 21:
                continue

            signal = self.pipeline.evaluate(
                asset,
                [candle["close"] for candle in candles],
                candles=list(candles),
            )
            asset_diagnostics = dict(self.pipeline.last_diagnostics)
            asset_diagnostics["asset"] = asset
            asset_diagnostics["candle_count"] = len(candles)
            diagnostics[asset] = asset_diagnostics

            if signal is not None:
                cooldown_active = monotonic() < self._cooldown_until.get(
                    signal.asset, 0.0
                )
                asset_diagnostics["cooldown_active"] = cooldown_active
                if cooldown_active:
                    continue

                candle_timestamp = float(
                    self._candle_timestamps[signal.asset][-1]
                )
                asset_diagnostics["signal_candle_timestamp"] = candle_timestamp
                if self._last_trade_candle.get(signal.asset) == candle_timestamp:
                    asset_diagnostics["same_candle_blocked"] = True
                    continue

                if self.external_synchronizer is not None:
                    match = self.external_synchronizer.compare(
                        signal.asset,
                        signal.direction,
                    )
                    asset_diagnostics["external_signal"] = (
                        match.external.direction if match else "NONE"
                    )
                    asset_diagnostics["external_match"] = (
                        match.matched if match else False
                    )
                    if match is None or not match.matched:
                        continue

                candidates.append(signal)

        selected = (
            max(candidates, key=lambda signal: signal.confidence)
            if candidates
            else None
        )
        return selected, diagnostics

    def amount_for_signal(self, signal: Signal) -> float:
        """Choose stake from signal quality, capped by configured risk."""
        confidence = float(signal.confidence)
        if confidence >= 80.0:
            risk_percent = self.max_risk_percent
        elif confidence >= 70.0:
            risk_percent = self.strong_risk_percent
        else:
            risk_percent = self.base_risk_percent

        risk_amount = self.starting_balance * risk_percent / 100.0
        return max(1.0, min(risk_amount, self.starting_balance * self.max_risk_percent / 100.0))

    async def open_trade(self, signal: Signal, price: float) -> TradeResult:
        amount = self.amount_for_signal(signal)
        request = TradeRequest(
            asset=signal.asset,
            direction=signal.direction,
            amount=amount,
            expiration_seconds=self.expiration_seconds,
        )
        result = await self.executor.execute(request)

        if result.accepted:
            if self.external_synchronizer is not None:
                self.external_synchronizer.consume(signal.asset)
            self._cooldown_until[signal.asset] = (
                monotonic() + self.cooldown_seconds
            )
            if self._candle_timestamps[signal.asset]:
                self._last_trade_candle[signal.asset] = self._candle_timestamps[
                    signal.asset
                ][-1]

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
