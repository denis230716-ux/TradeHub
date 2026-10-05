from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

from app.core.paper_trader import DemoPaperTrader
from app.execution.executor import PocketOptionDemoExecutor
from app.market.market_data import PocketOptionMarketData


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    asset = os.environ.get("POCKET_OPTION_ASSET", "")
    amount = float(os.environ.get("POCKET_OPTION_AMOUNT", "1"))
    expiration = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
    timeout = float(os.environ.get("POCKET_OPTION_STRATEGY_TIMEOUT", "86400"))

    run_until_raw = os.environ.get("POCKET_OPTION_RUN_UNTIL", "").strip()
    run_until = None
    if run_until_raw:
        try:
            run_until = datetime.fromisoformat(
                run_until_raw.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise RuntimeError(
                "POCKET_OPTION_RUN_UNTIL must be ISO-8601"
            ) from exc
        if run_until.tzinfo is None:
            run_until = run_until.replace(tzinfo=timezone.utc)

    evaluation_interval = max(
        1,
        int(os.environ.get("POCKET_OPTION_EVALUATION_INTERVAL", "5")),
    )

    market = None
    deadline = time.monotonic() + timeout
    if run_until is not None:
        remaining_until = (
            run_until - datetime.now(timezone.utc)
        ).total_seconds()
        deadline = min(
            deadline,
            time.monotonic() + max(0.0, remaining_until),
        )

    async def connect_market() -> PocketOptionMarketData:
        new_market = PocketOptionMarketData(session=ssid)
        if new_market.client is None:
            raise RuntimeError("Pocket Option transport is not initialized")
        await new_market.connect()
        assets = await new_market.available_assets(otc_only=True)
        if asset and asset in assets:
            assets = [asset] + [item for item in assets if item != asset]
        if not assets:
            await new_market.close()
            raise RuntimeError("No available OTC assets found")
        await new_market.subscribe_assets(
            assets,
            period=expiration,
            active_asset=asset or assets[0],
        )
        print(
            "MARKET_SUBSCRIPTIONS "
            f"assets={len(assets)} "
            f"active_asset={asset or assets[0]}"
        )
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
            f"timeout={timeout}s amount={amount} "
            f"expiration={expiration}s "
            f"run_until={run_until.isoformat() if run_until else 'none'}"
        )
        print("MODE=DEMO_ONLY LIVE_TRADING_BLOCKED")

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                async for snapshot in market.stream(timeout=remaining):
                    trader.ingest(snapshot)
                    snapshots += 1
                    if snapshots < 21 or snapshots % evaluation_interval:
                        continue

                    evaluations += 1
                    signal, diagnostics_by_asset = (
                        trader.evaluate_with_diagnostics()
                    )

                    if diagnostics_by_asset:
                        ranked = sorted(
                            diagnostics_by_asset.values(),
                            key=lambda item: max(
                                float(item.get("buy_score", 0.0)),
                                float(item.get("sell_score", 0.0)),
                            ),
                            reverse=True,
                        )
                        for diagnostics in ranked[:3]:
                            print(
                                "ASSET_ANALYSIS "
                                f"n={snapshots} "
                                f"asset={diagnostics.get('asset', 'n/a')} "
                                f"price={float(trader.history[diagnostics['asset']][-1]):.8f} "
                                f"signal={diagnostics.get('signal', 'HOLD')} "
                                f"signal_confidence={float(diagnostics.get('signal_confidence', 0.0)):.2f} "
                                f"decision_stage={diagnostics.get('decision_stage', 'n/a')} "
                                f"entry_status={diagnostics.get('entry_status', 'n/a')} "
                                f"cooldown_active={diagnostics.get('cooldown_active', False)} "
                                f"buy_score={float(diagnostics.get('buy_score', 0.0)):.1f} "
                                f"sell_score={float(diagnostics.get('sell_score', 0.0)):.1f} "
                                f"prediction={float(diagnostics.get('prediction_change', 0.0)):.6f}% "
                                f"prediction_confidence={float(diagnostics.get('prediction_confidence', 0.0)):.2f} "
                                f"allowed={diagnostics.get('trading_allowed', False)}"
                            )

                        for diagnostics in diagnostics_by_asset.values():
                            if diagnostics.get("signal") in {"CALL", "PUT"}:
                                status = diagnostics.get(
                                    "entry_status",
                                    "PIPELINE_BLOCKED",
                                )
                                if status not in {"READY", "SIGNAL_READY"}:
                                    print(
                                        "SIGNAL_BLOCK "
                                        f"asset={diagnostics.get('asset', 'n/a')} "
                                        f"direction={diagnostics.get('signal', 'n/a')} "
                                        f"confidence={float(diagnostics.get('signal_confidence', 0.0)):.1f} "
                                        f"stage={diagnostics.get('decision_stage', 'n/a')} "
                                        f"status={status} "
                                        f"cooldown={diagnostics.get('cooldown_active', False)}"
                                    )

                    if signal is None:
                        print("DECISION HOLD reason=conditions_not_met")
                        continue

                    print(
                        "DECISION "
                        f"{signal.direction} "
                        f"confidence={signal.confidence:.1f} "
                        f"reason={signal.reason}"
                    )
                    print(
                        "STRATEGY_ORDER "
                        f"asset={signal.asset} direction={signal.direction} "
                        f"amount={amount} expiration={expiration}s"
                    )

                    selected_price = float(trader.history[signal.asset][-1])
                    result = await trader.open_trade(signal, selected_price)
                    print(
                        "ORDER_RESULT "
                        f"accepted={result.accepted} "
                        f"trade_id={result.trade_id} reason={result.reason}"
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
            f"snapshots={snapshots} evaluations={evaluations} orders={orders}"
        )
        if snapshots == 0:
            raise RuntimeError("No Demo market snapshots were received")
    finally:
        if market is not None:
            await market.close()


if __name__ == "__main__":
    asyncio.run(main())
