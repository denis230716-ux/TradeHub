from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(slots=True)
class SignalResult:
    symbol: str
    signal: str
    confidence: float
    score: float
    buy_score: float
    sell_score: float
    trend: float
    momentum: float
    rsi: float
    reasons: List[str]


class SignalGenerator:
    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        self.min_buy_score = float(config.get("min_buy_score", 55))
        self.min_buy_difference = float(config.get("min_buy_difference", 20))
        self.min_sell_score = float(config.get("min_sell_score", 55))
        self.rsi_oversold = float(config.get("rsi_oversold", 35))
        self.rsi_overbought = float(config.get("rsi_overbought", 75))

    def generate_signal(self, symbol: str, analysis: Dict) -> SignalResult:
        buy = sell = 0.0
        reasons = []
        trend = float(analysis.get("trend", 0))
        momentum = float(analysis.get("momentum", 0))
        rsi = float(analysis.get("rsi", 50))

        if trend >= 0.30: buy += 15; reasons.append("strong uptrend")
        elif trend >= 0.10: buy += 10
        elif trend > 0: buy += 5
        elif trend <= -0.30: sell += 15; reasons.append("strong downtrend")
        elif trend < 0: sell += 5

        if momentum >= 0.30: buy += 12; reasons.append("strong momentum")
        elif momentum >= 0.10: buy += 8
        elif momentum > 0: buy += 4
        elif momentum <= -0.30: sell += 12
        elif momentum < 0: sell += 4

        if rsi <= self.rsi_oversold: buy += 15; reasons.append("oversold")
        elif rsi >= self.rsi_overbought: sell += 15; reasons.append("overbought")

        if analysis.get("near_support"): buy += 8
        if analysis.get("near_resistance"): sell += 8

        difference = buy - sell
        if buy >= self.min_buy_score and difference >= self.min_buy_difference:
            signal = "CALL"
        elif sell >= self.min_sell_score and difference <= -self.min_buy_difference:
            signal = "PUT"
        else:
            signal = "HOLD"

        total = max(buy, sell)
        confidence = min(100.0, total)
        return SignalResult(symbol, signal, confidence, total, buy, sell, trend, momentum, rsi, reasons)
