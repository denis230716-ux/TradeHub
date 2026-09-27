from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from app.core.paper_trader import DemoPaperTrader
from app.execution.executor import PocketOptionDemoExecutor
from app.market.market_data import PocketOptionMarketData
from app.strategy.scalping_guard import ScalpingGuard


@dataclass(slots=True)
class CalibrationStats:
    evaluations: int = 0
    buy_max: float = 0.0
    sell_max: float = 0.0
    buy_gap_min: float = 999.0
    sell_gap_min: float = 999.0
    guard_pass: int = 0
    guard_fail: int = 0
    aligned_buy: int = 0
    aligned_sell: int = 0


def component_scores(d: dict) -> tuple[float, float]:
    trend = float(d.get("trend", 0.0))
    momentum = float(d.get("momentum", 0.0))
    rsi = float(d.get("rsi", 50.0))
    buy = sell = 0.0

    if trend >= 0.30:
        buy += 15
    elif trend >= 0.10:
        buy += 10
    elif trend > 0:
        buy += 5
    elif trend <= -0.30:
        sell += 15
    elif trend < 0:
        sell += 5

    if momentum >= 0.30:
        buy += 12
    elif momentum >= 0.10:
        buy += 8
    elif momentum > 0:
        buy += 4
    elif momentum <= -0.30:
        sell += 12
    elif momentum < 0:
        sell += 4

    if rsi <= 35:
        buy += 15
    elif rsi >= 75:
        sell += 15

    if d.get("near_support"):
        buy += 8
    if d.get("near_resistance"):
        sell += 8
    return buy, sell


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
    period = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
    timeout = float(os.environ.get("POCKET_OPTION_CALIBRATION_TIMEOUT", "300"))

    market = PocketOptionMarketData(session=ssid)
    if market.client is None:
        raise RuntimeError("Pocket Option transport is not initialized")

    executor = PocketOptionDemoExecutor(market.client)
    trader = DemoPaperTrader(executor=executor, amount=1.0, expiration_seconds=period)
    guard = ScalpingGuard()
    stats = CalibrationStats()
    snapshots = 0

    try:
        await market.connect()
        await market.subscribe(asset, period=period)
        print(f"CALIBRATION_START asset={asset} period={period}s timeout={timeout:.0f}s")
        print("MODE=DEMO_ONLY LIVE_TRADING_BLOCKED")
        print("NO_ORDERS=true")
        print("CURRENT_SCORE_THRESHOLDS buy>=55 sell>=55 difference>=20")
        print(
            "CURRENT_SCALPING_GUARD "
            f"required_move={guard.required_entry_gross_profit_percent():.3f}%"
        )

        async for snapshot in market.stream(timeout=timeout):
            trader.ingest(snapshot)
            snapshots += 1
            if snapshots < 21 or snapshots % 10 != 0:
                continue

            trader.evaluate()
            d = trader.pipeline.last_diagnostics
            buy, sell = component_scores(d)
            prediction = float(d.get("prediction_change", 0.0))
            confidence = float(d.get("prediction_confidence", 0.0))
            guard_decision = guard.evaluate(abs(prediction))
            stats.evaluations += 1
            stats.buy_max = max(stats.buy_max, buy)
            stats.sell_max = max(stats.sell_max, sell)
            stats.buy_gap_min = min(stats.buy_gap_min, max(0.0, 55.0 - buy))
            stats.sell_gap_min = min(stats.sell_gap_min, max(0.0, 55.0 - sell))
            stats.guard_pass += int(guard_decision.allowed)
            stats.guard_fail += int(not guard_decision.allowed)

            if prediction > 0 and buy > sell:
                stats.aligned_buy += 1
            if prediction < 0 and sell > buy:
                stats.aligned_sell += 1

            print(
                f"CALIBRATION n={snapshots} buy={buy:.0f} sell={sell:.0f} "
                f"buy_gap={max(0, 55-buy):.0f} sell_gap={max(0, 55-sell):.0f} "
                f"prediction={prediction:.6f}% confidence={confidence:.2f} "
                f"guard={'PASS' if guard_decision.allowed else 'FAIL'} "
                f"direction={'BUY' if prediction > 0 else 'SELL' if prediction < 0 else 'FLAT'}"
            )

        print(
            "CALIBRATION_SUMMARY "
            f"snapshots={snapshots} evaluations={stats.evaluations} "
            f"buy_max={stats.buy_max:.0f} sell_max={stats.sell_max:.0f} "
            f"min_buy_gap={stats.buy_gap_min:.0f} min_sell_gap={stats.sell_gap_min:.0f} "
            f"guard_pass={stats.guard_pass} guard_fail={stats.guard_fail} "
            f"aligned_buy={stats.aligned_buy} aligned_sell={stats.aligned_sell}"
        )
        if snapshots == 0:
            raise RuntimeError("No Demo market snapshots were received")
    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
