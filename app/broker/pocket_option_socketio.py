from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

DEFAULT_URL = "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
DEFAULT_ORIGIN = "https://pocketoption.com"


class PocketOptionSocketIO:
    """Raw Socket.IO-over-WebSocket market-data transport.

    This adapter implements Demo connection and market-data subscription only.
    It deliberately does not send order/deal commands.
    """

    def __init__(
        self,
        auth_frame: str,
        *,
        url: str = DEFAULT_URL,
        origin: str = DEFAULT_ORIGIN,
    ) -> None:
        self.auth_frame = auth_frame.strip()
        self.url = url
        self.origin = origin
        self.ws: Any = None
        self.authenticated = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.events: list[str] = []
        self.assets: list[dict[str, Any]] = []
        self.stream_updates: list[Any] = []
        self.history_updates: list[Any] = []
        self.chart_updates: list[Any] = []
        self._reader_task: asyncio.Task[None] | None = None

    def _record(self, event: str) -> None:
        if event not in self.events:
            self.events.append(event)

    @staticmethod
    def _authorization(frame: str) -> dict[str, Any]:
        if not frame.startswith('42["auth",'):
            raise ValueError("POCKET_OPTION_SSID must be a complete auth frame")
        payload = json.loads(frame[2:])
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError("invalid Pocket Option auth frame")
        data = payload[1]
        if not isinstance(data, dict) or data.get("isDemo") != 1:
            raise ValueError("POCKET_OPTION_SSID must be a Demo auth frame")
        return data

    def _decode_assets(self, data: Any) -> None:
        rows = data
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return
        if len(rows) == 1 and isinstance(rows[0], list):
            rows = rows[0]

        for row in rows:
            if isinstance(row, dict):
                self.assets.append(row)
                continue
            if not isinstance(row, list) or len(row) < 2:
                continue
            symbol = row[1]
            if not isinstance(symbol, str) or not symbol.strip():
                continue
            self.assets.append(
                {
                    "id": row[0],
                    "symbol": symbol,
                    "name": row[2] if len(row) > 2 else symbol,
                    "category": row[3] if len(row) > 3 else "unknown",
                    "payout": row[5] if len(row) > 5 else 0,
                    "is_available": row[14] if len(row) > 14 else False,
                    "timeframes": row[15] if len(row) > 15 else [],
                    "raw": row,
                }
            )

    def _decode(self, message: str) -> None:
        if not isinstance(message, str):
            return
        if message == "2":
            if self.ws is not None:
                asyncio.create_task(self.ws.send("3"))
            return
        if not message.startswith("42"):
            return

        try:
            packet = json.loads(message[2:])
        except json.JSONDecodeError:
            return
        if not isinstance(packet, list) or not packet:
            return

        event = packet[0]
        data = packet[1] if len(packet) > 1 else None
        if not isinstance(event, str):
            return

        self._record(event)
        if event == "successauth":
            self.authenticated.set()
        elif event == "updateAssets":
            self._decode_assets(data)
        elif event == "updateStream":
            self.stream_updates.append(data)
        elif event == "updateHistoryNewFast":
            self.history_updates.append(data)
        elif event == "updateCharts":
            self.chart_updates.append(data)

    async def _reader(self) -> None:
        try:
            async for message in self.ws:
                self._decode(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.disconnected.set()
        finally:
            self.disconnected.set()

    async def connect(self) -> None:
        auth = self._authorization(self.auth_frame)
        self.ws = await websockets.connect(
            self.url,
            additional_headers={"Origin": self.origin},
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
            close_timeout=5,
        )

        first = await asyncio.wait_for(self.ws.recv(), timeout=10)
        if isinstance(first, bytes) or not str(first).startswith("0"):
            raise RuntimeError("unexpected Engine.IO handshake")

        await self.ws.send("40")
        connected = await asyncio.wait_for(self.ws.recv(), timeout=10)
        if isinstance(connected, bytes) or not str(connected).startswith("40"):
            raise RuntimeError("Socket.IO connection was not established")

        await self.ws.send(
            "42" + json.dumps(["auth", auth], separators=(",", ":"))
        )

        self._reader_task = asyncio.create_task(self._reader())
        await asyncio.wait_for(self.authenticated.wait(), timeout=15)

    async def wait_for_assets(self, timeout: float = 20) -> list[dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + timeout
        while not self.assets:
            if self.disconnected.is_set():
                break
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(0.25, remaining))
        return list(self.assets)

    async def subscribe(self, asset: str, period: int = 60) -> None:
        if self.ws is None:
            raise RuntimeError("Pocket Option WebSocket is not connected")
        await self.ws.send(
            "42"
            + json.dumps(
                ["changeSymbol", {"asset": asset, "period": period}],
                separators=(",", ":"),
            )
        )
        await self.ws.send(
            "42" + json.dumps(["subscribeSymbol", asset], separators=(",", ":"))
        )
        await self.ws.send(
            "42" + json.dumps(["subfor", asset], separators=(",", ":"))
        )

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
        self.disconnected.set()


