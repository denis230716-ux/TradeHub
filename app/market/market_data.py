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

    Pocket Option updateHistoryNewFast candle rows are:
    [timestamp, open, close, high, low, volume].
    """

    def __init__(
        self,
        session: str | None = None,
        token: str | None = None,
        client: PocketOptionSocketIO | None = None,
        stale_timeout: float = 30.0,
    ) -> None:
        self.session = session
        self.token = token
        self.client = client or (
            PocketOptionSocketIO(session) if session else None
        )
        self.stale_timeout = max(1.0, float(stale_timeout))

    @staticmethod
    def _timestamp(value: Any) -> float | None:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        return timestamp

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
        """Decode OHLCV candles, with legacy history compatibility."""
        if not isinstance(data, dict):
            return []

        asset = data.get("asset")
        candles = data.get("candles")
        history = data.get("history")
        period = data.get("period")

        if not isinstance(asset, str) or not asset.strip():
            return []

        snapshots: list[MarketSnapshot] = []

        # Verified live Demo payload: [timestamp, open, close, high, low, volume].
        if isinstance(candles, list):
            for row in candles:
                if not isinstance(row, (list, tuple)) or len(row) < 5:
                    continue

                timestamp = cls._timestamp(row[0])
                if timestamp is None:
                    continue

                try:
                    open_price = float(row[1])
                    close_price = float(row[2])
                    high_price = float(row[3])
                    low_price = float(row[4])
                    volume = float(row[5]) if len(row) > 5 else 0.0
                except (TypeError, ValueError):
                    continue

                if min(open_price, close_price, high_price, low_price) <= 0:
                    continue
                if high_price < max(open_price, close_price):
                    continue
                if low_price > min(open_price, close_price):
                    continue
                if volume < 0:
                    continue

                snapshots.append(
                    MarketSnapshot(
                        asset=asset,
                        price=close_price,
                        timestamp=datetime.fromtimestamp(
                            timestamp,
                            tz=timezone.utc,
                        ),
                        features={
                            "source": "pocket_option_updateHistoryNewFast",
                            "period": period,
                            "candle": {
                                "open": open_price,
                                "close": close_price,
                                "high": high_price,
                                "low": low_price,
                                "volume": volume,
                                "timestamp": timestamp,
                                "period": period,
                            },
                            "candles": candles,
                        },
                    )
                )

        # Backward compatibility for older payloads where history is tick data.
        if not snapshots and isinstance(history, list):
            for row in history:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue

                timestamp = cls._timestamp(row[0])
                if timestamp is None:
                    continue

                try:
                    price = float(row[1])
                except (TypeError, ValueError):
                    continue

                if price <= 0:
                    continue

                snapshots.append(
                    MarketSnapshot(
                        asset=asset,
                        price=price,
                        timestamp=datetime.fromtimestamp(
                            timestamp,
                            tz=timezone.utc,
                        ),
                        features={
                            "source": "pocket_option_history_legacy",
                            "period": period,
                            "candles": candles,
                        },
                    )
                )

        return sorted(snapshots, key=lambda snapshot: snapshot.timestamp)

    @classmethod
    def decode_stream_update(
        cls,
        data: Any,
        candle_period: int = 5,
    ) -> list[MarketSnapshot]:
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

            numeric_timestamp = cls._timestamp(timestamp)
            if numeric_timestamp is None:
                continue

            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue

            if numeric_price <= 0:
                continue

            snapshots.append(
                MarketSnapshot(
                    asset=asset,
                    price=numeric_price,
                    timestamp=datetime.fromtimestamp(
                        numeric_timestamp,
                        tz=timezone.utc,
                    ),
                    features={
                        "source": "pocket_option_updateStream",
                        "period": candle_period,
                        "candle": {
                            "open": numeric_price,
                            "high": numeric_price,
                            "low": numeric_price,
                            "close": numeric_price,
                            "volume": 0.0,
                            "timestamp": float(
                                int(numeric_timestamp) // candle_period
                                * candle_period
                            ),
                            "period": candle_period,
                        },
                    },
                )
            )

        return snapshots

    async def available_assets(
        self,
        timeout: float = 20.0,
        otc_only: bool = True,
    ) -> list[str]:
        if self.client is None:
            raise RuntimeError(
                "Pocket Option Demo auth frame is not configured"
            )
        assets = await self.client.available_assets(timeout=timeout)
        if otc_only:
            assets = [asset for asset in assets if asset.endswith("_otc")]
        return list(dict.fromkeys(assets))

    async def connect(self) -> None:
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")
        await self.client.connect()

    async def subscribe_signals(self) -> None:
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")
        await self.client.subscribe_signals()

    async def subscribe(self, asset: str, period: int = 5) -> None:
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")
        await self.client.subscribe(asset, period=period)

    async def stream(self, timeout: float = 30.0):
        """Yield verified history candles first, then realtime Demo ticks."""
        if self.client is None:
            raise RuntimeError("Pocket Option Demo auth frame is not configured")

        history_index = 0
        stream_index = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        last_fresh_update = loop.time()
        last_stream_signature: dict[str, tuple[float, float]] = {}

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
                    signature = (
                        snapshot.timestamp.timestamp(),
                        snapshot.price,
                    )
                    if last_stream_signature.get(snapshot.asset) == signature:
                        continue
                    last_stream_signature[snapshot.asset] = signature
                    last_fresh_update = loop.time()
                    yield snapshot

            if self.client.disconnected.is_set():
                reason = self.client.disconnect_reason
                if reason:
                    raise RuntimeError(
                        f"Pocket Option WebSocket disconnected: {reason}"
                    )
                break
            if not progressed:
                if loop.time() - last_fresh_update >= self.stale_timeout:
                    raise RuntimeError(
                        "Pocket Option market data became stale; reconnect required"
                    )
                await asyncio.sleep(0.1)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
