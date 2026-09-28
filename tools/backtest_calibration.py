from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from app.market.market_data import PocketOptionMarketData
from app.ml.predictor import MarketPredictor
from app.signals.generator import SignalGenerator
from app.strategy.indicators import calculate_momentum, calculate_rsi
from app.strategy.market_analysis import MarketAnalysis


@dataclass(slots=True)
class Sample:
    buy: float
    sell: float
    prediction: float
    index: int
    close: float


@dataclass(slots=True)
class Result:
    signals: int = 0
    wins: int = 0
    losses: int = 0

    @property
    def win_rate(self) -> float:
        decided = self.wins + self.losses
        return self.wins / decided * 100 if decided else 0.0


def score_direction(
    buy: float,
    sell: float,
    buy_threshold: float,
    sell_threshold: float,
    difference: float,
) -> str:
    gap = buy - sell
    if buy >= buy_threshold and gap >= difference:
        return "CALL"
    if sell >= sell_threshold and gap <= -difference:
        return "PUT"
    return "HOLD"


def evaluate_config(
    samples: list[Sample],
    closes: list[float],
    start: int,
    end: int,
    buy_threshold: float,
    sell_threshold: float,
    difference: float,
    guard_threshold: float,
    horizon: int,
) -> Result:
    result = Result()
    for sample in samples:
        if sample.index < start or sample.index >= end:
            continue
        if sample.index + horizon >= len(closes):
            continue
        if abs(sample.prediction) < guard_threshold:
            continue

        direction = score_direction(
            sample.buy,
            sample.sell,
            buy_threshold,
            sell_threshold,
            difference,
        )
        if direction == "HOLD":
            continue

        result.signals += 1
        future = closes[sample.index + horizon]
        if direction == "CALL":
            if future > sample.close:
                result.wins += 1
            elif future < sample.close:
                result.losses += 1
        else:
            if future < sample.close:
                result.wins += 1
            elif future > sample.close:
                result.losses += 1
    return result


def build_samples(candles: list[dict], asset: str) -> list[Sample]:
    analysis_engine = MarketAnalysis()
    predictor = MarketPredictor()
    generator = SignalGenerator()
    closes = [float(c["close"]) for c in candles]
    samples: list[Sample] = []

    for index in range(20, len(candles)):
        window = candles[: index + 1]
        market = analysis_engine.analyze(window)
        if not market.trading_allowed:
            continue

        prices = closes[: index + 1]
        prediction = predictor.predict(asset, prices)
        current = prediction.current_price
        prediction_change = (
            (prediction.predicted_price - current) / current * 100
            if current > 0 else 0.0
        )
        analysis = {
            "trend": market.trend_percent,
            "momentum": calculate_momentum(prices, 5) or 0.0,
            "rsi": calculate_rsi(prices, 14) or 50.0,
            "near_support": market.near_support,
            "near_resistance": market.near_resistance,
            "prediction_change": prediction_change,
            "prediction_confidence": prediction.confidence,
        }
        generated = generator.generate_signal(asset, analysis)
        samples.append(
            Sample(
                buy=generated.buy_score,
                sell=generated.sell_score,
                prediction=prediction_change,
                index=index,
                close=current,
            )
        )
    return samples


async def collect_full_history(
    market: PocketOptionMarketData,
    asset: str,
    period: int,
    timeout: float,
) -> list[dict]:
    deadline = asyncio.get_running_loop().time() + timeout
    collection_deadline: float | None = None
    history_index = 0
    candles_by_timestamp: dict[int, dict] = {}
    payload_counts: list[int] = []

    while asyncio.get_running_loop().time() < deadline:
        while history_index < len(market.client.history_updates):
            update = market.client.history_updates[history_index]
            history_index += 1
            if not isinstance(update, dict) or update.get("asset") != asset:
                continue
            if update.get("period") not in (None, period):
                continue

            candles = update.get("candles")
            history = update.get("history")
            if not isinstance(candles, list) and not isinstance(history, list):
                continue

            payload_count = len(candles) if isinstance(candles, list) else 0
            history_count = len(history) if isinstance(history, list) else 0
            payload_counts.append(payload_count)
            print(
                f"HISTORY_PAYLOAD asset={asset} period={update.get('period')} "
                f"candles_rows={payload_count} history_rows={history_count}"
            )

            now = asyncio.get_running_loop().time()
            if collection_deadline is None:
                collection_deadline = min(deadline, now + 10.0)

            if isinstance(candles, list):
                for row in candles:
                    if not isinstance(row, (list, tuple)) or len(row) < 5:
                        continue
                    try:
                        timestamp = int(float(row[0]))
                        open_price = float(row[1])
                        close_price = float(row[2])
                        high_price = float(row[3])
                        low_price = float(row[4])
                        volume = float(row[5]) if len(row) > 5 else 0.0
                    except (TypeError, ValueError):
                        continue
                    if min(open_price, close_price, high_price, low_price) <= 0:
                        continue
                    if high_price < max(open_price, close_price):
                        continue
                    if low_price > min(open_price, close_price):
                        continue
                    if volume < 0:
                        continue
                    candles_by_timestamp[timestamp] = {
                        "timestamp": timestamp,
                        "open": open_price,
                        "close": close_price,
                        "high": high_price,
                        "low": low_price,
                        "volume": volume,
                    }

            if isinstance(history, list):
                for row in history:
                    if not isinstance(row, (list, tuple)) or len(row) < 2:
                        continue
                    try:
                        timestamp = int(float(row[0]))
                        close_price = float(row[1])
                    except (TypeError, ValueError):
                        continue
                    if close_price <= 0:
                        continue
                    if timestamp in candles_by_timestamp:
                        continue
                    candles_by_timestamp[timestamp] = {
                        "timestamp": timestamp,
                        "open": close_price,
                        "close": close_price,
                        "high": close_price,
                        "low": close_price,
                        "volume": 0.0,
                    }

        if collection_deadline is not None and asyncio.get_running_loop().time() >= collection_deadline:
            break
        if market.client.disconnected.is_set():
            break
        await asyncio.sleep(0.1)

    if payload_counts:
        print(
            f"HISTORY_SUMMARY payloads={len(payload_counts)} "
            f"payload_max={max(payload_counts)} "
            f"payload_min={min(payload_counts)} "
            f"unique_candles={len(candles_by_timestamp)}"
        )

    return [
        candles_by_timestamp[key]
        for key in sorted(candles_by_timestamp)
    ]


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
    period = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
    timeout = float(os.environ.get("POCKET_OPTION_BACKTEST_TIMEOUT", "300"))
    horizon = int(os.environ.get("POCKET_OPTION_BACKTEST_HORIZON", "1"))

    market = PocketOptionMarketData(session=ssid)
    if market.client is None:
        raise RuntimeError("Pocket Option transport is not initialized")

    try:
        await market.connect()
        await market.subscribe(asset, period=period)
        print(
            f"BACKTEST_START asset={asset} period={period}s "
            f"timeout={timeout:.0f}s"
        )
        print("MODE=DEMO_ONLY LIVE_TRADING_BLOCKED")
        print("NO_ORDERS=true")

        candles = await collect_full_history(
            market, asset, period, timeout
        )
        if len(candles) < 60:
            raise RuntimeError(
                f"Not enough unique OHLCV candles: {len(candles)}"
            )

        closes = [c["close"] for c in candles]
        samples = build_samples(candles, asset)
        split_index = int(len(candles) * 0.60)

        print(
            f"DATA candles={len(candles)} samples={len(samples)} "
            f"split={split_index}"
        )
        print(
            f"DATA_RANGE first={candles[0]['timestamp']} "
            f"last={candles[-1]['timestamp']}"
        )
        print(
            f"HORIZON candles={horizon} seconds={horizon * period}"
        )
        print(
            "CURRENT_CONFIG buy>=55 sell>=55 difference>=20 guard>=0.100%"
        )

        current_train = evaluate_config(
            samples, closes, 20, split_index,
            55, 55, 20, 0.10, horizon
        )
        current_val = evaluate_config(
            samples, closes, split_index, len(candles) - horizon,
            55, 55, 20, 0.10, horizon
        )
        print(
            "CURRENT_RESULT "
            f"train_signals={current_train.signals} "
            f"train_win_rate={current_train.win_rate:.2f}% "
            f"validation_signals={current_val.signals} "
            f"validation_win_rate={current_val.win_rate:.2f}%"
        )

        candidates = []
        for threshold in (15, 20, 25, 30, 35, 40, 45, 50, 55):
            for difference in (0, 5, 10, 15, 20):
                for guard in (0.0, 0.02, 0.05, 0.10):
                    train = evaluate_config(
                        samples, closes, 20, split_index,
                        threshold, threshold, difference, guard, horizon
                    )
                    validation = evaluate_config(
                        samples, closes, split_index, len(candles) - horizon,
                        threshold, threshold, difference, guard, horizon
                    )
                    if train.signals < 10 or validation.signals < 10:
                        continue
                    candidates.append(
                        (
                            validation.win_rate,
                            validation.signals,
                            train.win_rate,
                            threshold,
                            difference,
                            guard,
                            train,
                            validation,
                        )
                    )

        candidates.sort(
            key=lambda x: (x[0], x[1], x[2]),
            reverse=True,
        )
        if not candidates:
            print(
                "CALIBRATION_CANDIDATES "
                "none_with_minimum_10_signals_each_split=true"
            )
        else:
            print(
                "CALIBRATION_CANDIDATES "
                "top=12 sorted_by_validation_win_rate"
            )
            for rank, item in enumerate(candidates[:12], 1):
                (
                    val_rate,
                    _,
                    train_rate,
                    threshold,
                    difference,
                    guard,
                    train,
                    validation,
                ) = item
                print(
                    f"CANDIDATE rank={rank} score={threshold} "
                    f"diff={difference} guard={guard:.3f}% "
                    f"train={train.signals}/{train_rate:.2f}% "
                    f"validation={validation.signals}/{val_rate:.2f}%"
                )

        for test_horizon in (1, 3):
            current = evaluate_config(
                samples, closes, split_index, len(candles) - test_horizon,
                55, 55, 20, 0.10, test_horizon
            )
            print(
                f"ROBUSTNESS horizon={test_horizon} "
                f"seconds={test_horizon * period} "
                f"validation_signals={current.signals} "
                f"validation_win_rate={current.win_rate:.2f}%"
            )

        print("BACKTEST_COMPLETED no_orders=true")
    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
