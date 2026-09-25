import pytest

from app.broker.pocket_option import PocketOptionExecutor
from app.broker.pocket_option_transport import (
    PocketOptionSession,
    UnconfiguredPocketOptionTransport,
)
from app.core.models import TradeRequest


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
