from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import socketio


DEFAULT_WS_URL = (
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket"
)
DEFAULT_ORIGIN = "https://pocketoption.com"


class PocketOptionSocketIO:
    """Pocket Option Socket.IO market-data transport.

    This adapter intentionally implements market-data only. It does not emit
    order/deal commands, keeping Demo discovery fail-closed.
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
        self.sio = socketio.AsyncClient(
            reconnection=False,
            logger=False,
            engineio_logger=False,
        )
        self.authenticated = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.events: list[str] = []
        self.assets: list[dict[str, Any]] = []
        self.stream_updates: list[Any] = []
        self.history_updates: list[Any] = []
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.sio.event
        async def disconnect() -> None:
            self.disconnected.set()

        @self.sio.on("successauth")
        async def successauth(data: Any = None) -> None:
            self._record("successauth")
            self.authenticated.set()

        @self.sio.on("updateAssets")
        async def update_assets(data: Any = None) -> None:
            self._record("updateAssets")
            if isinstance(data, list):
                self.assets.extend(
                    item for item in data if isinstance(item, dict)
                )
            elif isinstance(data, dict):
                self.assets.append(data)

        @self.sio.on("updateStream")
        async def update_stream(data: Any = None) -> None:
            self._record("updateStream")
            self.stream_updates.append(data)

        @self.sio.on("updateHistoryNewFast")
        async def update_history(data: Any = None) -> None:
            self._record("updateHistoryNewFast")
            self.history_updates.append(data)

        @self.sio.on("*")
        async def any_event(event: str, data: Any = None) -> None:
            if event not in self.events:
                self.events.append(event)

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

    async def connect(self) -> None:
        auth = self._authorization(self.auth_frame)
        headers = {"Origin": self.origin}
        await self.sio.connect(
            self.url,
            headers=headers,
            transports=["websocket"],
            socketio_path="socket.io",
            wait=True,
            wait_timeout=15,
            auth=None,
        )
        await self.sio.emit("auth", auth)
        await asyncio.wait_for(self.authenticated.wait(), timeout=15)

    async def wait_for_assets(self, timeout: float = 20) -> list[dict[str, Any]]:
        deadline = asyncio.get_running_loop().time() + timeout
        while not self.assets:
            if self.disconnected.is_set():
                break
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(0.5, remaining))
        return list(self.assets)

    async def subscribe(self, asset: str, period: int = 60) -> None:
        await self.sio.emit("changeSymbol", {"asset": asset, "period": period})
        await self.sio.emit("subscribeSymbol", asset)
        await self.sio.emit("subfor", asset)

    async def close(self) -> None:
        if self.sio.connected:
            await self.sio.disconnect()


AssetCallback = Callable[[list[dict[str, Any]]], Awaitable[None]]
