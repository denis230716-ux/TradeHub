from app.core.models import MarketSnapshot, Signal


class SignalEngine:
    def evaluate(self, market: MarketSnapshot) -> Signal | None:
        return None
