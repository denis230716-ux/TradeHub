from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.broker.pocket_option_socketio import PocketOptionSocketIO
from app.core.models import MarketSnapshot


class MarketDataProvider:
    async def stream(self):
        raise NotImplementedError


class PocketOptionMarketData(MarketDataProvider):
    """Verified Demo market-data adapter.

    It converts Pocket Option updateStream and updateHistoryNewFast
    payloads into MarketSnapshot objects. Order execution is intentionally
    outside this adapter.
    """

    def __init__(
        self,
        session: str | None = None,
        token: str | None = None,
        client: PocketOptionSocketIO | None = None,
    ) -> None:
        self.session = session
        self.token = token
        self.client = client or (
            PocketOptionSocketIO(session) if session else None
        )

    @staticmethod
    def _rows(data: Any) -> list[Any]:
        if isinstance(data, list) and data and isinstance(data[0], list):
            return data
        if isinstance(data, list) and len(data) >= 3:
            return [data]
        if isinstance(data, dict):
            return [data]
        return []

    @classmethod
    def decode_history_update(cls, data: Any) -> list[MarketSnapshot]:
        """Decode verified updateHistoryNewFast history rows."""
        if not isinstance(data, dict):
            return []

        asset = data.get("asset")
        history = data.get("history")
        if not isinstance(asset, str) or not asset.strip():
            return []
        if not isinstance(history, list):
            return []

        period = data.get("period")
        candles = data.get("candles")
        snapshots: list[MarketSnapshot] = []
        for row in history:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                numeric_timestamp = float(row[0])
                numeric_price = float(row[1])
            except (TypeError, ValueError):
                continue
            if numeric_price <= 0:
                continue
            if numeric_timestamp > 10_000_000_000:
                numeric_timestamp /= 1000.0

            snapshots.append(
                MarketSnapshot(
                    asset=asset,
                    price=numeric_price,
                    timestamp=datetime.fromtimestamp(
                        numeric_timestamp, tz=timezone.utc
                    ),
                    features={
                        "source": "pocket_option_updateHistoryNewFast",
                        "period": period,
                        "candles": candles,
                    },
                )
            )
        return snapshots

    @classmethod
    def decode_stream_update(cls, data: Any) -> list[MarketSnapshot]:
        """Decode the verified [asset, timestamp, price] tick format."""
        snapshots: list[MarketSnapshot] = []
        for row in cls._rows(data):
            if isinstance(row, dict):
                asset = row.get("asset") or row.get("symbol")
                timestamp = row.get("timestamp") or row.get("time")
                price = row.get("price") or row.get("value")
            else:
                if len(row) < 3:
                    continue
                asset, timestamp, price = row[0], row[1], row[2]

            if not isinstance(asset, str) or not asset.strip():
                continue
            try:
                numeric_price = float(price)
                numeric_timestamp = float(timestamp)
            except (TypeError, ValueError):
                continue
            if numeric_price <= 0:
                continue
            if numeric_timestamp > 10_000_000_000:
                numeric_timestamp /= 1000.0

            snapshots.append(
                MarketSnapshot(
                    asset=asset,
                    price=numeric_price,
                    timestamp=datetime.fromtimestamp(
                        numeric_timestamp, tz=timezone.utc
                    ),
                    features={"source": "pocket_option_updateStream"},
                )
            )
        return snapshots

    async def connect(self) -> None:
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")
        await self.client.connect()

    async def subscribe(self, asset: str, period: int = 5) -> None:
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")
        await self.client.subscribe(asset, period=period)

    async def stream(self, timeout: float = 30.0):
        """Yield verified history first, then realtime Demo ticks."""
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")

        history_index = 0
        stream_index = 0
        deadline = asyncio.get_running_loop().time() + timeout

        while asyncio.get_running_loop().time() < deadline:
            progressed = False

            while history_index < len(self.client.history_updates):
                update = self.client.history_updates[history_index]
                history_index += 1
                progressed = True
                for snapshot in self.decode_history_update(update):
                    yield snapshot

            while stream_index < len(self.client.stream_updates):
                update = self.client.stream_updates[stream_index]
                stream_index += 1
                progressed = True
                for snapshot in self.decode_stream_update(update):
                    yield snapshot

            if self.client.disconnected.is_set():
                break
            if not progressed:
                await asyncio.sleep(0.1)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
