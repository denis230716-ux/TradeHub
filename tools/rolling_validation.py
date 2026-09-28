from __future__ import annotations

import asyncio
import os

from tools.backtest_calibration import (
    build_samples,
    collect_full_history,
    evaluate_config,
)
from app.market.market_data import PocketOptionMarketData


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
    period = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
    timeout = float(os.environ.get("POCKET_OPTION_BACKTEST_TIMEOUT", "300"))
    horizon = int(os.environ.get("POCKET_OPTION_BACKTEST_HORIZON", "1"))

    market = PocketOptionMarketData(session=ssid)
    try:
        await market.connect()
        await market.subscribe(asset, period=period)
        print(
            f"ROLLING_VALIDATION_START asset={asset} period={period}s "
            f"timeout={timeout:.0f}s"
        )
        print("MODE=DEMO_ONLY LIVE_TRADING_BLOCKED")
        print("NO_ORDERS=true")

        candles = await collect_full_history(market, asset, period, timeout)
        if len(candles) < 120:
            raise RuntimeError(f"Not enough candles: {len(candles)}")

        closes = [float(c["close"]) for c in candles]
        samples = build_samples(candles, asset)
        n = len(candles)

        config = (15, 15, 10, 0.0)
        print("CONFIG score=15 diff=10 guard=0.000%")

        windows = [
            ("W1", 20, n // 4),
            ("W2", n // 4, n // 2),
            ("W3", n // 2, (3 * n) // 4),
            ("W4", (3 * n) // 4, n - horizon),
        ]

        total_signals = 0
        total_wins = 0
        total_losses = 0

        for name, start, end in windows:
            result = evaluate_config(
                samples, closes, start, end,
                config[0], config[1], config[2], config[3], horizon
            )
            total_signals += result.signals
            total_wins += result.wins
            total_losses += result.losses
            print(
                f"WINDOW name={name} start={start} end={end} "
                f"signals={result.signals} win_rate={result.win_rate:.2f}% "
                f"wins={result.wins} losses={result.losses}"
            )

        decided = total_wins + total_losses
        overall = total_wins / decided * 100 if decided else 0.0
        print(
            f"ROLLING_SUMMARY windows={len(windows)} signals={total_signals} "
            f"win_rate={overall:.2f}% wins={total_wins} losses={total_losses}"
        )
        print("ROLLING_VALIDATION_COMPLETED no_orders=true")
    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
