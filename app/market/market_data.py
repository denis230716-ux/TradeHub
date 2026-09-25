from abc import ABC, abstractmethod
from app.core.models import MarketSnapshot


class MarketDataProvider(ABC):
    @abstractmethod
    async def stream(self):
        raise NotImplementedError


class PocketOptionMarketData(MarketDataProvider):
    """Pocket Option market-data adapter.

    Protocol-specific websocket/session handling will live here so the
    strategy layer remains independent of the broker transport.
    """

    def __init__(self, session: str | None = None, token: str | None = None):
        self.session = session
        self.token = token

    async def stream(self):
        raise NotImplementedError("Pocket Option realtime adapter is not wired yet")
