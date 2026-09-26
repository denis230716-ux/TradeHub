from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor
from typing import Iterable

from app.core.models import MarketSnapshot


@dataclass(frozen=True, slots=True)
class Candle:
    asset: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


def build_candles(
    snapshots: Iterable[MarketSnapshot],
    period_seconds: int = 5,
) -> list[Candle]:
    """Build OHLC candles from verified price snapshots.

    Timestamps are assigned to fixed UTC buckets of period_seconds.
    Volume is the number of price updates in each bucket.
    """
    if period_seconds <= 0:
        raise ValueError("period_seconds must be positive")

    ordered = sorted(snapshots, key=lambda item: item.timestamp)
    buckets: dict[tuple[str, int], list[float]] = {}

    for snapshot in ordered:
        epoch = snapshot.timestamp.astimezone(timezone.utc).timestamp()
        bucket = int(floor(epoch / period_seconds) * period_seconds)
        buckets.setdefault((snapshot.asset, bucket), []).append(snapshot.price)

    candles: list[Candle] = []
    for (asset, bucket), prices in sorted(buckets.items(), key=lambda item: item[0][1]):
        candles.append(
            Candle(
                asset=asset,
                timestamp=datetime.fromtimestamp(bucket, tz=timezone.utc),
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=len(prices),
            )
        )

    return candles
