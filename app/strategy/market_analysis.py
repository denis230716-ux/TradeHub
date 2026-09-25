from dataclasses import dataclass
from typing import Any, List


@dataclass(slots=True)
class MarketAnalysisResult:
    state: str
    trend_percent: float
    volatility_percent: float
    current_volume: float
    average_volume: float
    volume_ratio: float
    volume_state: str
    support: float
    resistance: float
    near_support: bool
    near_resistance: bool
    trading_allowed: bool
    reason: str


class MarketAnalysis:
    def __init__(
        self,
        short_period: int = 5,
        long_period: int = 20,
        volume_period: int = 20,
        volatility_limit: float = 3.0,
    ):
        self.short_period = int(short_period)
        self.long_period = int(long_period)
        self.volume_period = int(volume_period)
        self.volatility_limit = float(volatility_limit)

    @staticmethod
    def _value(candle: Any, field: str, default: float = 0.0) -> float:
        try:
            value = candle.get(field, default) if isinstance(candle, dict) else getattr(candle, field, default)
            return float(value)
        except (TypeError, ValueError):
            return default

    def analyze(self, candles: List[Any]) -> MarketAnalysisResult:
        closes = [self._value(c, "close") for c in candles if self._value(c, "close") > 0]
        volumes = [self._value(c, "volume") for c in candles if self._value(c, "volume") >= 0]

        if len(closes) < max(self.long_period, 2):
            return MarketAnalysisResult(
                "INSUFFICIENT_DATA", 0, 0, 0, 0, 0, "UNKNOWN",
                0, 0, False, False, False, "not enough candles"
            )

        short_avg = sum(closes[-self.short_period:]) / self.short_period
        long_avg = sum(closes[-self.long_period:]) / self.long_period
        trend = (short_avg - long_avg) / long_avg * 100 if long_avg else 0

        changes = [
            (b - a) / a * 100
            for a, b in zip(closes, closes[1:])
            if a > 0
        ]
        volatility = sum(abs(x) for x in changes[-self.long_period:]) / max(1, len(changes[-self.long_period:]))

        support = min(closes[-self.long_period:])
        resistance = max(closes[-self.long_period:])
        price = closes[-1]
        range_size = max(resistance - support, price * 0.0001)
        proximity = range_size * 0.10

        avg_volume = sum(volumes[-self.volume_period:]) / max(1, len(volumes[-self.volume_period:]))
        current_volume = volumes[-1] if volumes else 0.0
        ratio = current_volume / avg_volume if avg_volume > 0 else 0.0
        volume_state = "VERY_HIGH" if ratio >= 2 else "HIGH" if ratio >= 1.25 else "NORMAL" if ratio >= 0.75 else "LOW"

        if volatility > self.volatility_limit:
            state = "HIGH_VOLATILITY"
        elif trend >= 0.10:
            state = "UPTREND"
        elif trend <= -0.10:
            state = "DOWNTREND"
        else:
            state = "SIDEWAYS"

        allowed = state != "HIGH_VOLATILITY" and volatility <= self.volatility_limit
        return MarketAnalysisResult(
            state, trend, volatility, current_volume, avg_volume, ratio,
            volume_state, support, resistance,
            abs(price - support) <= proximity,
            abs(resistance - price) <= proximity,
            allowed,
            "market conditions accepted" if allowed else "market conditions rejected",
        )
