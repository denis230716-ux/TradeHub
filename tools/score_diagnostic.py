from __future__ import annotations

import asyncio
import os

from app.core.paper_trader import DemoPaperTrader
from app.execution.executor import PocketOptionDemoExecutor
from app.market.market_data import PocketOptionMarketData


def component_scores(diagnostics: dict) -> dict[str, float]:
    trend = float(diagnostics.get("trend", 0.0))
    momentum = float(diagnostics.get("momentum", 0.0))
    rsi = float(diagnostics.get("rsi", 50.0))
    buy = 0.0
    sell = 0.0
    if trend >= 0.30: buy += 15
    elif trend >= 0.10: buy += 10
    elif trend > 0: buy += 5
    elif trend <= -0.30: sell += 15
    elif trend < 0: sell += 5
    if momentum >= 0.30: buy += 12
    elif momentum >= 0.10: buy += 8
    elif momentum > 0: buy += 4
    elif momentum <= -0.30: sell += 12
    elif momentum < 0: sell += 4
    if rsi <= 35: buy += 15
    elif rsi >= 75: sell += 15
    if diagnostics.get("near_support"): buy += 8
    if diagnostics.get("near_resistance"): sell += 8
    return {
        "trend_buy": 15.0 if trend >= 0.30 else 10.0 if trend >= 0.10 else 5.0 if trend > 0 else 0.0,
        "trend_sell": 15.0 if trend <= -0.30 else 5.0 if trend < 0 else 0.0,
        "momentum_buy": 12.0 if momentum >= 0.30 else 8.0 if momentum >= 0.10 else 4.0 if momentum > 0 else 0.0,
        "momentum_sell": 12.0 if momentum <= -0.30 else 4.0 if momentum < 0 else 0.0,
        "rsi_buy": 15.0 if rsi <= 35 else 0.0,
        "rsi_sell": 15.0 if rsi >= 75 else 0.0,
        "support_buy": 8.0 if diagnostics.get("near_support") else 0.0,
        "resistance_sell": 8.0 if diagnostics.get("near_resistance") else 0.0,
        "buy_total": buy, "sell_total": sell,
    }


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid: raise RuntimeError("POCKET_OPTION_SSID secret is not configured")
    asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
    expiration = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
    timeout = float(os.environ.get("POCKET_OPTION_SCORE_TIMEOUT", "30"))
    market = PocketOptionMarketData(session=ssid)
    if market.client is None: raise RuntimeError("Pocket Option transport is not initialized")
    executor = PocketOptionDemoExecutor(market.client)
    trader = DemoPaperTrader(executor=executor, amount=1.0, expiration_seconds=expiration)
    snapshots = 0; evaluations = 0
    try:
        await market.connect(); await market.subscribe(asset, period=expiration)
        print(f"SCORE_DIAGNOSTIC_START asset={asset}")
        print("MODE=DEMO_ONLY LIVE_TRADING_BLOCKED")
        print("SIGNAL_THRESHOLDS buy>=55 sell>=55 difference>=20")
        async for snapshot in market.stream(timeout=timeout):
            trader.ingest(snapshot); snapshots += 1
            if snapshots < 21 or snapshots % 10 != 0: continue
            evaluations += 1; trader.evaluate()
            diagnostics = trader.pipeline.last_diagnostics
            scores = component_scores(diagnostics)
            print(
                f"SCORE n={snapshots} "
                f"trend_buy={scores['trend_buy']:.0f} trend_sell={scores['trend_sell']:.0f} "
                f"momentum_buy={scores['momentum_buy']:.0f} momentum_sell={scores['momentum_sell']:.0f} "
                f"rsi_buy={scores['rsi_buy']:.0f} rsi_sell={scores['rsi_sell']:.0f} "
                f"support_buy={scores['support_buy']:.0f} resistance_sell={scores['resistance_sell']:.0f} "
                f"buy={scores['buy_total']:.0f} sell={scores['sell_total']:.0f} "
                f"buy_gap={55-scores['buy_total']:.0f} sell_gap={55-scores['sell_total']:.0f} "
                f"prediction_confidence={float(diagnostics.get('prediction_confidence', 0.0)):.2f} "
                f"prediction={float(diagnostics.get('prediction_change', 0.0)):.6f}%"
            )
        print(f"SCORE_DIAGNOSTIC_COMPLETED snapshots={snapshots} evaluations={evaluations}")
        if snapshots == 0: raise RuntimeError("No Demo market snapshots were received")
    finally: await market.close()

if __name__ == "__main__": asyncio.run(main())