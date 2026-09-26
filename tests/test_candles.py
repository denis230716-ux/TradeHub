from datetime import datetime, timezone

from app.core.models import MarketSnapshot
from app.market.candles import build_candles


def snapshot(asset: str, second: float, price: float) -> MarketSnapshot:
    return MarketSnapshot(
        asset=asset,
        price=price,
        timestamp=datetime.fromtimestamp(second, tz=timezone.utc),
        features={},
    )


def test_build_five_second_ohlc_candle():
    candles = build_candles(
        [
            snapshot("EURJPY_otc", 1000.2, 181.095),
            snapshot("EURJPY_otc", 1001.0, 181.097),
            snapshot("EURJPY_otc", 1004.9, 181.090),
        ],
        period_seconds=5,
    )

    assert len(candles) == 1
    candle = candles[0]
    assert candle.asset == "EURJPY_otc"
    assert candle.open == 181.095
    assert candle.high == 181.097
    assert candle.low == 181.090
    assert candle.close == 181.090
    assert candle.volume == 3
    assert candle.timestamp == datetime.fromtimestamp(1000, tz=timezone.utc)


def test_build_candles_keeps_assets_and_time_buckets_separate():
    candles = build_candles(
        [
            snapshot("EURJPY_otc", 1000.1, 181.10),
            snapshot("EURJPY_otc", 1005.1, 181.20),
            snapshot("GBPUSD_otc", 1000.2, 1.2500),
        ],
        period_seconds=5,
    )

    assert len(candles) == 3
    assert {(item.asset, item.volume) for item in candles} == {
        ("EURJPY_otc", 1),
        ("GBPUSD_otc", 1),
    } | {("EURJPY_otc", 1)}


def test_build_candles_rejects_invalid_period():
    try:
        build_candles([], period_seconds=0)
    except ValueError as exc:
        assert str(exc) == "period_seconds must be positive"
    else:
        raise AssertionError("Expected ValueError")
