from __future__ import annotations

import asyncio
import os
import time

from app.core.paper_trader import DemoPaperTrader
from app.execution.executor import PocketOptionDemoExecutor
from app.market.market_data import PocketOptionMarketData


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()

    if not ssid:
        raise RuntimeError(
            "POCKET_OPTION_SSID secret is not configured"
        )

    asset = os.environ.get(
        "POCKET_OPTION_ASSET",
        "",
    )

    amount = float(
        os.environ.get(
            "POCKET_OPTION_AMOUNT",
            "1",
        )
    )

    expiration = int(
        os.environ.get(
            "POCKET_OPTION_PERIOD",
            "5",
        )
    )

    timeout = float(
        os.environ.get(
            "POCKET_OPTION_STRATEGY_TIMEOUT",
            "86400",
        )
    )


    trader = None
    market = None
    deadline = time.monotonic() + timeout

    async def connect_market() -> PocketOptionMarketData:
        new_market = PocketOptionMarketData(session=ssid)
        if new_market.client is None:
            raise RuntimeError(
                "Pocket Option transport is not initialized"
            )
        await new_market.connect()
        assets = await new_market.available_assets(otc_only=True)
        if asset and asset in assets:
            assets = [asset] + [item for item in assets if item != asset]
        if not assets:
            await new_market.close()
            raise RuntimeError("No available OTC assets found")
        for candidate in assets:
            await new_market.subscribe(candidate, period=expiration)
        return new_market

    snapshots = 0
    evaluations = 0
    orders = 0

    try:
        market = await connect_market()
        trader = DemoPaperTrader(
            executor=PocketOptionDemoExecutor(market.client),
            amount=amount,
            expiration_seconds=expiration,
        )

        print(
            "STRATEGY_TEST_START "
            f"timeout={timeout}s "
            f"amount={amount} "
            f"expiration={expiration}s"
        )

        print(
            "MODE=DEMO_ONLY "
            "LIVE_TRADING_BLOCKED"
        )

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                async for snapshot in market.stream(timeout=remaining):
            trader.ingest(snapshot)
            snapshots += 1

                if snapshots < 21:
                    continue

                if snapshots % 10 != 0:
                    continue

                evaluations += 1

                signal, diagnostics_by_asset = trader.evaluate_with_diagnostics()

                if diagnostics_by_asset:
                    ranked = sorted(
                        diagnostics_by_asset.values(),
                        key=lambda item: max(
                            float(item.get("buy_score", 0.0)),
                            float(item.get("sell_score", 0.0)),
                        ),
                        reverse=True,
                    )
                    top = ranked[:3]
                    for diagnostics in top:
                        print(
                            "ASSET_ANALYSIS "
                            f"n={snapshots} "
                            f"asset={diagnostics.get('asset', 'n/a')} "
                            f"price={float(trader.history[diagnostics['asset']][-1]):.8f} "
                            f"state={diagnostics.get('market_state', 'n/a')} "
                            f"trend={float(diagnostics.get('trend', 0.0)):.6f}% "
                            f"momentum={float(diagnostics.get('momentum', 0.0)):.6f}% "
                            f"rsi={float(diagnostics.get('rsi', 50.0)):.2f} "
                            f"support={diagnostics.get('near_support', False)} "
                            f"resistance={diagnostics.get('near_resistance', False)} "
                            f"prediction={float(diagnostics.get('prediction_change', 0.0)):.6f}% "
                            f"prediction_confidence={float(diagnostics.get('prediction_confidence', 0.0)):.2f} "
                            f"buy_score={float(diagnostics.get('buy_score', 0.0)):.1f} "
                            f"sell_score={float(diagnostics.get('sell_score', 0.0)):.1f} "
                            f"signal={diagnostics.get('signal', 'HOLD')} "
                            f"signal_confidence={float(diagnostics.get('signal_confidence', 0.0)):.2f} "
                            f"prediction_confidence={float(diagnostics.get('prediction_confidence', 0.0)):.2f} "
                            f"allowed={diagnostics.get('trading_allowed', False)}"
                        )

                if signal is None:
                    print(
                        "DECISION "
                        "HOLD "
                        f"reason=conditions_not_met"
                    )
                    continue

                print(
                    "DECISION "
                    f"{signal.direction} "
                    f"confidence={signal.confidence:.1f} "
                    f"reason={signal.reason}"
                )

                print(
                    "STRATEGY_ORDER "
                    f"asset={signal.asset} "
                    f"direction={signal.direction} "
                    f"amount={amount} "
                    f"expiration={expiration}s"
                )

                selected_price = float(
                    trader.history[signal.asset][-1]
                )
                result = await trader.open_trade(
                    signal,
                    selected_price,
                )

                print(
                    "ORDER_RESULT "
                    f"accepted={result.accepted} "
                    f"trade_id={result.trade_id} "
                    f"reason={result.reason}"
                )

                if result.accepted:
                    orders += 1

                except RuntimeError as exc:
                    if time.monotonic() >= deadline:
                        break
                    print(f"STRATEGY_RECONNECT reason={exc}")
                    if market is not None:
                        await market.close()
                    await asyncio.sleep(1)
                    market = await connect_market()
                    trader.executor = PocketOptionDemoExecutor(market.client)

        print(
            "STRATEGY_TEST_COMPLETED "
            f"snapshots={snapshots} "
            f"evaluations={evaluations} "
            f"orders={orders}"
        )

        if snapshots == 0:
            raise RuntimeError(
                "No Demo market snapshots were received"
            )

    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
