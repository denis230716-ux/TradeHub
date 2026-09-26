import asyncio
from datetime import datetime, timezone

from app.core.models import MarketSnapshot
from app.core.paper_trader import DemoPaperTrader


def snapshot(asset: str, price: float) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        price=price,
        timestamp=datetime.now(timezone.utc),
        features={},
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
    signal = __import__("app.core.models", fromlist=["Signal"]).Signal(
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
