import math
from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class Prediction:
    symbol: str
    current_price: float
    predicted_price: float
    confidence: float


class MarketPredictor:
    """Short-horizon statistical predictor ported from Galaxy."""

    def __init__(self, lookback_period: int = 20, min_prices: int = 20, forecast_horizon: int = 3):
        self.lookback_period = max(6, int(lookback_period))
        self.min_prices = max(2, int(min_prices))
        self.forecast_horizon = max(1, int(forecast_horizon))

    @staticmethod
    def _valid_prices(prices: List[float]) -> List[float]:
        result = []
        for price in prices:
            try:
                value = float(price)
                if value > 0 and math.isfinite(value):
                    result.append(value)
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def calculate_returns(prices: List[float]) -> List[float]:
        return [
            (current - previous) / previous * 100
            for previous, current in zip(prices, prices[1:])
            if previous > 0
        ]

    @staticmethod
    def _mean(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def calculate_volatility(self, returns: List[float]) -> float:
        if len(returns) < 2:
            return 0.0
        average = self._mean(returns)
        variance = sum((value - average) ** 2 for value in returns) / len(returns)
        return math.sqrt(max(0.0, variance))

    def _momentum(self, prices: List[float], period: int) -> float:
        if len(prices) <= period or prices[-period - 1] <= 0:
            return 0.0
        return (prices[-1] - prices[-period - 1]) / prices[-period - 1] * 100

    def _acceleration(self, returns: List[float]) -> float:
        if len(returns) < 4:
            return 0.0
        return self._mean(returns[-2:]) - self._mean(returns[-4:-2])

    def _linear_slope(self, prices: List[float]) -> float:
        values = prices[-min(10, len(prices)):]
        if len(values) < 3:
            return 0.0
        x_mean = (len(values) - 1) / 2
        y_mean = self._mean(values)
        denominator = sum((i - x_mean) ** 2 for i in range(len(values)))
        if denominator == 0 or y_mean <= 0:
            return 0.0
        numerator = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
        return numerator / denominator / y_mean * 100

    def _forecast_move(self, prices: List[float], returns: List[float]) -> float:
        recent = self._mean(returns[-5:])
        broader = self._mean(returns[-10:])
        momentum_3 = self._momentum(prices, 3)
        momentum_5 = self._momentum(prices, 5)
        acceleration = self._acceleration(returns)
        slope = self._linear_slope(prices)

        per_candle = (
            recent * 0.35 + broader * 0.20
            + (momentum_3 / 3.0) * 0.25
            + (momentum_5 / 5.0) * 0.20
            + acceleration * 0.20 + slope * 0.25
        )
        expected = per_candle * self.forecast_horizon
        if momentum_3 > 0 and momentum_5 > 0:
            expected *= 1.10
        elif momentum_3 < 0 and momentum_5 < 0:
            expected *= 1.10

        volatility = self.calculate_volatility(returns)
        max_move = max(0.40, volatility * 2.5 * math.sqrt(self.forecast_horizon))
        return max(-max_move, min(expected, max_move))

    def predict(self, symbol: str, prices: List[float]) -> Prediction:
        valid = self._valid_prices(prices)
        if not valid:
            raise ValueError("price history is empty")
        current = valid[-1]
        if len(valid) < 2:
            return Prediction(symbol, current, current, 5.0)

        lookback = valid[-self.lookback_period:]
        returns = self.calculate_returns(lookback)
        if not returns:
            return Prediction(symbol, current, current, 5.0)

        volatility = self.calculate_volatility(returns)
        trend = (lookback[-1] - lookback[0]) / lookback[0] * 100
        direction = self._mean(returns)
        consistency = (
            sum((value > 0) == (direction > 0) for value in returns) / len(returns)
            if direction else 0.0
        )
        half = len(returns) // 2
        old = self._mean(returns[:half])
        new = self._mean(returns[half:])
        momentum_consistency = (
            1.0 if old and new and ((old > 0) == (new > 0))
            else 0.35 if old and new else 0.5
        )

        momentum_3 = self._momentum(lookback, 3)
        momentum_5 = self._momentum(lookback, 5)
        acceleration = self._acceleration(returns)
        slope = self._linear_slope(lookback)
        votes = [momentum_3, momentum_5, acceleration, slope, trend]
        alignment = max(sum(v > 0 for v in votes), sum(v < 0 for v in votes)) / 5

        expected = self._forecast_move(lookback, returns)
        predicted = current * (1 + expected / 100)
        data_score = min(len(valid) / max(self.lookback_period, 1), 1)
        volatility_score = max(0, min(1, 1 - volatility / 2.5))
        confidence = (
            data_score * 20 + volatility_score * 10
            + max(0, min(consistency, 1)) * 30
            + max(0, min(momentum_consistency, 1)) * 15
            + alignment * 25
        )
        return Prediction(symbol, current, predicted, max(5.0, min(confidence, 90.0)))
