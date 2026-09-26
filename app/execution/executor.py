from abc import ABC, abstractmethod

from app.core.models import TradeRequest, TradeResult


class TradeExecutor(ABC):
    @abstractmethod
    async def execute(self, request: TradeRequest) -> TradeResult:
        raise NotImplementedError


class DryRunExecutor(TradeExecutor):
    async def execute(self, request: TradeRequest) -> TradeResult:
        return TradeResult(
            accepted=True,
            trade_id="DRY_RUN",
            reason="simulation",
        )


class PocketOptionDemoExecutor(TradeExecutor):
    """Executes orders only through a verified Pocket Option Demo session."""

    def __init__(self, transport):
        self.transport = transport

    async def execute(self, request: TradeRequest) -> TradeResult:
        if request.amount <= 0:
            return TradeResult(
                accepted=False,
                reason="amount must be positive",
            )

        if request.direction not in {"CALL", "PUT"}:
            return TradeResult(
                accepted=False,
                reason="direction must be CALL or PUT",
            )

        try:
            data = await self.transport.open_order(
                asset=request.asset,
                amount=request.amount,
                direction=request.direction,
                expiration_seconds=request.expiration_seconds,
            )
        except Exception as exc:
            return TradeResult(
                accepted=False,
                reason=str(exc),
            )

        trade_id = None

        if isinstance(data, dict):
            trade_id = str(
                data.get("id")
                or data.get("tradeId")
                or data.get("orderId")
                or ""
            ) or None

        return TradeResult(
            accepted=True,
            trade_id=trade_id,
            reason="Pocket Option Demo order accepted",
        )
