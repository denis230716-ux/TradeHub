import pytest

from app.broker.pocket_option import PocketOptionExecutor
from app.broker.pocket_option_transport import (
    PocketOptionSession,
    UnconfiguredPocketOptionTransport,
)
from app.core.models import TradeRequest


class FakeTransport:
    async def connect(self, session: PocketOptionSession) -> None:
        session.connected = True

    async def close(self) -> None:
        return None

    async def receive(self):
        return {}

    async def send(self, payload):
        return None


@pytest.mark.asyncio
async def test_live_execution_is_disabled_by_default():
    executor = PocketOptionExecutor(session="test-session")
    result = await executor.execute(
        TradeRequest(
            asset="TEST",
            direction="CALL",
            amount=1.0,
            expiration_seconds=5,
        )
    )
    assert result.accepted is False
    assert "disabled" in result.reason


@pytest.mark.asyncio
async def test_unconfigured_transport_fails_closed():
    transport = UnconfiguredPocketOptionTransport()
    with pytest.raises(RuntimeError):
        await transport.connect(PocketOptionSession())


@pytest.mark.asyncio
async def test_live_mode_does_not_invent_order_protocol():
    executor = PocketOptionExecutor(
        session="test-session",
        transport=FakeTransport(),
        live_enabled=True,
    )
    with pytest.raises(NotImplementedError):
        await executor.execute(
            TradeRequest(
                asset="TEST",
                direction="CALL",
                amount=1.0,
                expiration_seconds=5,
            )
        )


from app.market.market_data import PocketOptionMarketData


def test_decode_pocket_option_stream_tick():
    snapshots = PocketOptionMarketData.decode_stream_update(
        ["EURJPY_otc", 1758883200, 123.456]
    )
    assert len(snapshots) == 1
    assert snapshots[0].asset == "EURJPY_otc"
    assert snapshots[0].price == 123.456
    assert snapshots[0].timestamp.tzinfo is not None


def test_decode_pocket_option_stream_batch():
    snapshots = PocketOptionMarketData.decode_stream_update(
        [
            ["EURUSD", 1758883200, 1.2345],
            ["GBPUSD", 1758883201, 1.3456],
        ]
    )
    assert [item.asset for item in snapshots] == ["EURUSD", "GBPUSD"]


def test_decode_invalid_stream_payload():
    assert PocketOptionMarketData.decode_stream_update({"unexpected": True}) == []


def test_decode_pocket_option_history_update():
    payload = {
        "asset": "EURJPY_otc",
        "period": 5,
        "history": [
            [1790425318.715, 181.095],
            [1790425319.245, 181.097],
        ],
        "candles": [{"opaque": "kept"}],
    }
    snapshots = PocketOptionMarketData.decode_history_update(payload)
    assert len(snapshots) == 2
    assert snapshots[0].asset == "EURJPY_otc"
    assert snapshots[0].price == 181.095
    assert snapshots[0].features["period"] == 5
    assert snapshots[0].features["candles"] == [{"opaque": "kept"}]


def test_decode_invalid_pocket_option_history_update():
    assert PocketOptionMarketData.decode_history_update({"asset": "EURJPY_otc"}) == []
