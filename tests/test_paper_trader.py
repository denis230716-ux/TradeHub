import asyncio
from datetime import datetime, timezone

from app.core.models import MarketSnapshot, Signal
from app.core.paper_trader import DemoPaperTrader
from app.execution.executor import DryRunExecutor


def snapshot(asset: str, price: float) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        price=price,
        timestamp=datetime.now(timezone.utc),
        features={},
    )


def candle_snapshot(asset: str, price: float, timestamp: float) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        price=price,
        timestamp=datetime.now(timezone.utc),
        features={
            "candle": {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 1.0,
                "timestamp": timestamp,
            }
        },
    )


class AlwaysCallPipeline:
    def __init__(self):
        self.last_diagnostics = {
            "signal": "CALL",
            "signal_confidence": 80.0,
            "decision_stage": "SIGNAL_READY",
        }

    def evaluate(self, asset, prices, candles=None):
        return Signal(
            asset=asset,
            direction="CALL",
            confidence=80.0,
            timestamp=datetime.now(timezone.utc),
            reason="test",
        )


def test_paper_trader_keeps_separate_history_per_asset():
    trader = DemoPaperTrader()
    trader.ingest(snapshot("EURUSD", 1.1))
    trader.ingest(snapshot("GBPUSD", 1.2))
    trader.ingest(snapshot("EURUSD", 1.11))

    assert list(trader.history["EURUSD"]) == [1.1, 1.11]
    assert list(trader.history["GBPUSD"]) == [1.2]


def test_paper_trader_waits_for_enough_history():
    trader = DemoPaperTrader()
    for i in range(20):
        trader.ingest(snapshot("EURUSD", 1.0 + i * 0.001))
    assert trader.evaluate() is None


def test_paper_trade_never_leaves_dry_run():
    trader = DemoPaperTrader()
    signal = Signal(
        asset="EURUSD",
        direction="CALL",
        confidence=80.0,
        timestamp=datetime.now(timezone.utc),
        reason="test",
    )
    result = asyncio.run(trader.open_virtual_trade(signal, 1.1234))
    assert result.accepted is True
    assert result.trade_id == "DRY-000001"
    assert "simulation" in result.reason


def test_paper_trader_adapts_stake_to_signal_confidence():
    trader = DemoPaperTrader(starting_balance=921.15)
    now = datetime.now(timezone.utc)

    base = Signal("EURUSD", "CALL", 60.0, now)
    strong = Signal("EURUSD", "CALL", 75.0, now)
    max_signal = Signal("EURUSD", "CALL", 90.0, now)

    assert trader.amount_for_signal(base) == 4.60575
    assert trader.amount_for_signal(strong) == 6.908625
    assert trader.amount_for_signal(max_signal) == 9.2115
    assert trader.amount_for_signal(max_signal) <= 921.15 * 0.01


def test_paper_trader_allows_signal_after_previous_same_candle_trade():
    trader = DemoPaperTrader(
        pipeline=AlwaysCallPipeline(),
        executor=DryRunExecutor(),
        cooldown_seconds=0,
    )

    for i in range(21):
        trader.ingest(candle_snapshot("EURUSD", 1.0 + i * 0.001, 1000.0 + i))

    asyncio.run(
        trader.open_trade(
            Signal(
                "EURUSD",
                "CALL",
                80.0,
                datetime.now(timezone.utc),
                "test",
            ),
            1.02,
        )
    )

    signal, diagnostics = trader.evaluate_with_diagnostics()

    assert signal is not None
    assert signal.direction == "CALL"
    assert diagnostics["EURUSD"]["entry_status"] == "READY"
    assert "same_candle_blocked" not in diagnostics["EURUSD"]
