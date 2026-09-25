from app.core.models import TradeRequest, TradeResult
from app.execution.executor import TradeExecutor


class PocketOptionExecutor(TradeExecutor):
    """Broker adapter boundary for Pocket Option execution."""

    def __init__(self, session: str | None = None, token: str | None = None):
        self.session = session
        self.token = token

    async def execute(self, request: TradeRequest) -> TradeResult:
        raise NotImplementedError(
            "Pocket Option execution protocol must be implemented after "
            "the authenticated transport is verified."
        )
