import asyncio
from datetime import datetime, timezone

from app.core.models import MarketSnapshot, Signal
from app.core.paper_trader import DemoPaperTrader
from app.core.outcome_tracker import DemoOutcomeTracker
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


class CapturingExecutor(DryRunExecutor):
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return await super().execute(request)


def test_open_trade_respects_configured_fixed_stake():
    executor = CapturingExecutor()
    trader = DemoPaperTrader(executor=executor, amount=1.0)
    signal = Signal("EURUSD", "CALL", 95.0, datetime.now(timezone.utc))

    asyncio.run(trader.open_trade(signal, 1.1))

    assert len(executor.requests) == 1
    assert executor.requests[0].amount == 1.0


def test_outcome_tracker_estimates_call_win_and_summary():
    tracker = DemoOutcomeTracker(payout_rate=0.92)
    tracker.register(
        trade_id="demo-1", asset="EURUSD_otc", direction="CALL",
        amount=1.0, entry_price=1.1, expiration_seconds=5, opened_at=10.0,
    )

    assert tracker.on_quote("GBPUSD_otc", 1.2, now=16.0) == []
    outcomes = tracker.on_quote("EURUSD_otc", 1.1001, now=16.0)

    assert outcomes[0]["outcome_estimate"] == "WIN"
    assert outcomes[0]["estimated_net"] == 0.92
    summary = tracker.summary()
    assert summary["wins"] == 1
    assert summary["losses"] == 0
    assert summary["by_asset"]["EURUSD_otc"]["wins"] == 1
    assert summary["source"] == "ESTIMATES_ONLY_NOT_BROKER_SETTLEMENTS"


def test_outcome_tracker_estimates_put_loss_and_push_counts():
    tracker = DemoOutcomeTracker(payout_rate=0.92)
    tracker.register(
        trade_id="demo-2", asset="GBPUSD_otc", direction="PUT",
        amount=1.0, entry_price=1.2, expiration_seconds=5, opened_at=10.0,
    )
    tracker.on_quote("GBPUSD_otc", 1.21, now=15.0)

    tracker.register(
        trade_id="demo-3", asset="GBPUSD_otc", direction="CALL",
        amount=1.0, entry_price=1.2, expiration_seconds=5, opened_at=20.0,
    )
    tracker.on_quote("GBPUSD_otc", 1.2, now=25.0)

    summary = tracker.summary()
    assert summary["losses"] == 1
    assert summary["pushes"] == 1
    assert summary["by_direction"]["PUT"]["losses"] == 1
    assert summary["by_direction"]["CALL"]["pushes"] == 1
