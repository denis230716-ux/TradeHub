from __future__ import annotations

from app.broker.pocket_option_transport import (
    PocketOptionSession,
    PocketOptionTransport,
    UnconfiguredPocketOptionTransport,
)
from app.core.models import TradeRequest, TradeResult
from app.execution.executor import TradeExecutor


class PocketOptionExecutor(TradeExecutor):
    """Fail-closed Pocket Option execution boundary."""

    def __init__(
        self,
        session: str | None = None,
        token: str | None = None,
        transport: PocketOptionTransport | None = None,
        live_enabled: bool = False,
    ):
        self.session = PocketOptionSession(session=session, token=token)
        self.transport = transport or UnconfiguredPocketOptionTransport()
        self.live_enabled = bool(live_enabled)

    async def execute(self, request: TradeRequest) -> TradeResult:
        if not self.live_enabled:
            return TradeResult(
                accepted=False,
                reason="live Pocket Option execution is disabled",
            )

        if not self.session.session and not self.session.token:
            return TradeResult(
                accepted=False,
                reason="Pocket Option credentials are not configured",
            )

        await self.transport.connect(self.session)
        raise NotImplementedError(
            "Pocket Option order protocol is pending verified transport mapping"
        )
