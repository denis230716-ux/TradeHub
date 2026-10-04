from __future__ import annotations

import json

import pytest

from app.broker.pocket_option_socketio import PocketOptionSocketIO


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_bulk_subscription_does_not_change_chart_for_each_asset() -> None:
    client = PocketOptionSocketIO('42["auth",{"session":"x","isDemo":1}]')
    client.ws = FakeWebSocket()

    await client.subscribe_assets(
        ["EURUSD_otc", "GBPUSD_otc", "EURUSD_otc"],
        period=5,
        active_asset="GBPUSD_otc",
    )

    packets = [json.loads(message[2:]) for message in client.ws.messages]
    assert packets == [
        ["subscribeSymbol", "EURUSD_otc"],
        ["subfor", "EURUSD_otc"],
        ["subscribeSymbol", "GBPUSD_otc"],
        ["subfor", "GBPUSD_otc"],
        ["changeSymbol", {"asset": "GBPUSD_otc", "period": 5}],
    ]
