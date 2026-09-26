from __future__ import annotations

import asyncio
import os

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
        "EURJPY_otc",
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
            "30",
        )
    )

    max_orders = int(
        os.environ.get(
            "POCKET_OPTION_MAX_ORDERS",
            "1",
        )
    )

    market = PocketOptionMarketData(
        session=ssid
    )

    if market.client is None:
        raise RuntimeError(
            "Pocket Option transport is not initialized"
        )

    executor = PocketOptionDemoExecutor(
        market.client
    )

    trader = DemoPaperTrader(
        executor=executor,
        amount=amount,
        expiration_seconds=expiration,
    )

    snapshots = 0
    evaluations = 0
    orders = 0

    try:
        await market.connect()

        await market.subscribe(
            asset,
            period=expiration,
        )

        print(
            "STRATEGY_TEST_START "
            f"asset={asset} "
            f"amount={amount} "
            f"expiration={expiration}s"
        )

        print(
            "MODE=DEMO_ONLY "
            "LIVE_TRADING_BLOCKED"
        )

        async for snapshot in market.stream(
            timeout=timeout
        ):
            trader.ingest(snapshot)
            snapshots += 1

            if snapshots < 21:
                continue

            if snapshots % 10 != 0:
                continue

            evaluations += 1

            signal = trader.evaluate()
            diagnostics = trader.pipeline.last_diagnostics

            print(
                "ANALYSIS "
                f"n={snapshots} "
                f"price={snapshot.price} "
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

            if orders >= max_orders:
                print(
                    "ORDER_LIMIT_REACHED "
                    f"max_orders={max_orders}"
                )
                break

            print(
                "STRATEGY_ORDER "
                f"asset={signal.asset} "
                f"direction={signal.direction} "
                f"amount={amount} "
                f"expiration={expiration}s"
            )

            result = await trader.open_trade(
                signal,
                snapshot.price,
            )

            print(
                "ORDER_RESULT "
                f"accepted={result.accepted} "
                f"trade_id={result.trade_id} "
                f"reason={result.reason}"
            )

            if result.accepted:
                orders += 1
                break

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
