from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol


@dataclass(slots=True)
class PocketOptionSession:
    session: str | None = None
    token: str | None = None
    connected: bool = False


class PocketOptionTransport(Protocol):
    async def connect(self, session: PocketOptionSession) -> None: ...
    async def close(self) -> None: ...
    async def receive(self) -> dict[str, Any]: ...
    async def send(self, payload: dict[str, Any]) -> None: ...


class UnconfiguredPocketOptionTransport:
    """Safe transport placeholder.

    No undocumented Pocket Option endpoint or message format is assumed.
    This class deliberately fails closed until the verified transport is wired.
    """

    def __init__(self) -> None:
        self.session = PocketOptionSession()

    async def connect(self, session: PocketOptionSession) -> None:
        if not session.session and not session.token:
            raise RuntimeError("Pocket Option session credentials are not configured")
        raise NotImplementedError(
            "Pocket Option transport protocol is not configured yet"
        )

    async def close(self) -> None:
        self.session.connected = False

    async def receive(self) -> dict[str, Any]:
        raise RuntimeError("Pocket Option transport is not connected")

    async def send(self, payload: dict[str, Any]) -> None:
        raise RuntimeError("Pocket Option transport is not connected")
