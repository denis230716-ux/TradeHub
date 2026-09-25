from typing import List, Optional


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_prices(prices) -> List[float]:
    if not prices:
        return []
    return [value for value in (safe_float(p) for p in prices) if value > 0]


def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    prices = normalize_prices(prices)
    try:
        period = int(period)
    except (TypeError, ValueError):
        return None
    if period <= 0 or len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 6)


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    prices = normalize_prices(prices)
    try:
        period = int(period)
    except (TypeError, ValueError):
        return None
    if period <= 0 or len(prices) < period + 1:
        return None

    recent = prices[-(period + 1):]
    gains = []
    losses = []
    for previous, current in zip(recent, recent[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 6)


def calculate_momentum(prices: List[float], period: int = 5) -> Optional[float]:
    prices = normalize_prices(prices)
    if period <= 0 or len(prices) <= period:
        return None
    base = prices[-period - 1]
    if base <= 0:
        return None
    return round((prices[-1] - base) / base * 100.0, 6)
