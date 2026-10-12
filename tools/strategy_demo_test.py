from __future__ import annotations

import asyncio
import os
import time
from collections import Counter
from datetime import datetime, timezone

from app.core.paper_trader import DemoPaperTrader
from app.core.outcome_tracker import DemoOutcomeTracker
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

    evaluation_interval_seconds = max(
        0.25,
        float(os.environ.get("POCKET_OPTION_EVALUATION_INTERVAL_SECONDS", "1")),
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
    next_evaluation_at = 0.0
    asset_evaluation_counts: Counter[str] = Counter()
    last_snapshot_received_at: dict[str, float] = {}
    latest_snapshot_price: dict[str, float] = {}
    freshness_report_every = 30
    asset_signal_counts: Counter[str] = Counter()
    direction_candidate_counts: Counter[str] = Counter()
    selected_asset_counts: Counter[str] = Counter()
    selected_direction_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    decision_stage_counts: Counter[str] = Counter()
    outcome_tracker = DemoOutcomeTracker(
        payout_rate=float(os.environ.get("POCKET_OPTION_PAYOUT_RATE", "0.92"))
    )

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
                    last_snapshot_received_at[snapshot.asset] = time.monotonic()
                    latest_snapshot_price[snapshot.asset] = float(snapshot.price)
                    for outcome in outcome_tracker.on_quote(
                        snapshot.asset, snapshot.price
                    ):
                        print("TRADE_OUTCOME_ESTIMATE " + " ".join(
                            f"{key}={value}" for key, value in outcome.items()
                        ))
                    snapshots += 1
                    now = time.monotonic()
                    if snapshots < 21 or now < next_evaluation_at:
                        continue
                    next_evaluation_at = now + evaluation_interval_seconds

                    evaluations += 1
                    signal, diagnostics_by_asset = (
                        trader.evaluate_with_diagnostics()
                    )
                    for item in diagnostics_by_asset.values():
                        name = str(item.get("asset", "unknown"))
                        asset_evaluation_counts[name] += 1
                        last_seen = last_snapshot_received_at.get(name)
                        item["seconds_since_latest_snapshot"] = (
                            round(now - last_seen, 2) if last_seen is not None else -1.0
                        )
                        item["latest_snapshot_price"] = latest_snapshot_price.get(name, 0.0)
                        candle_times = trader._candle_timestamps.get(name)
                        item["latest_candle_timestamp"] = (
                            float(candle_times[-1]) if candle_times else 0.0
                        )
                        if item.get("signal") in {"CALL", "PUT"}:
                            asset_signal_counts[name] += 1
                            direction_candidate_counts[str(item["signal"])] += 1
                        stage = str(item.get("decision_stage", "unknown"))
                        decision_stage_counts[stage] += 1
                        raw_reasons = item.get("signal_rejection_reasons", [])
                        if isinstance(raw_reasons, str):
                            raw_reasons = [part for part in raw_reasons.replace(",", "|").split("|") if part]
                        if isinstance(raw_reasons, (list, tuple, set)):
                            rejection_counts.update(str(reason) for reason in raw_reasons if reason)

                    if evaluations % freshness_report_every == 0:
                        freshness = sorted(
                            (
                                (asset_name, round(now - seen_at, 2), latest_snapshot_price.get(asset_name, 0.0),
                                 float(trader._candle_timestamps[asset_name][-1]) if trader._candle_timestamps.get(asset_name) else 0.0,
                                 len(trader.candle_history.get(asset_name, ())))
                                for asset_name, seen_at in last_snapshot_received_at.items()
                            ),
                            key=lambda row: row[1],
                            reverse=True,
                        )
                        stale = [row for row in freshness if row[1] >= 10.0]
                        print(
                            "DATA_FRESHNESS "
                            f"evaluation={evaluations} subscribed_assets={len(last_snapshot_received_at)} "
                            f"stale_assets_10s={len(stale)} "
                            f"oldest_assets={[(a, age, price, candle_ts, candles) for a, age, price, candle_ts, candles in freshness[:8]]}"
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
                                f"hold_reasons={diagnostics.get('signal_rejection_reasons', 'n/a')} "
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
                        reasons = sorted({
                            str(item.get("signal_rejection_reasons", ""))
                            for item in diagnostics_by_asset.values()
                            if item.get("signal_rejection_reasons")
                        })
                        print(
                            "DECISION HOLD "
                            f"reason=conditions_not_met "
                            f"candidate_rejections={'|'.join(reasons[:8]) or 'no_directional_candidate'}"
                        )
                        continue

                    selected_diagnostics = diagnostics_by_asset.get(
                        signal.asset, {}
                    )
                    selected_asset_counts[signal.asset] += 1
                    selected_direction_counts[signal.direction] += 1
                    print(
                        "ASSET_SELECTED "
                        f"asset={signal.asset} "
                        f"direction={signal.direction} "
                        f"candidate_rank={selected_diagnostics.get('candidate_rank', 'n/a')} "
                        f"candidate_count={selected_diagnostics.get('candidate_count', 'n/a')} "
                        f"signal_score={float(selected_diagnostics.get('signal_score', 0.0)):.2f} "
                        f"buy_score={float(selected_diagnostics.get('buy_score', 0.0)):.2f} "
                        f"sell_score={float(selected_diagnostics.get('sell_score', 0.0)):.2f} "
                        f"prediction_confidence={float(selected_diagnostics.get('prediction_confidence', signal.confidence)):.2f} "
                        f"prediction_change={float(selected_diagnostics.get('prediction_change', 0.0)):.6f}% "
                        f"selection_reason={selected_diagnostics.get('selection_reason', 'n/a')} "
                        f"entry_status={selected_diagnostics.get('entry_status', 'n/a')} "
                        f"market_state={selected_diagnostics.get('market_state', 'n/a')} "
                        f"market_volatility={float(selected_diagnostics.get('market_volatility', 0.0)):.4f} "
                        f"trend={float(selected_diagnostics.get('trend', 0.0)):.4f} "
                        f"momentum={float(selected_diagnostics.get('momentum', 0.0)):.4f} "
                        f"rsi={float(selected_diagnostics.get('rsi', 50.0)):.2f}"
                    )
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
                    try:
                        result = await trader.open_trade(signal, selected_price)
                    except RuntimeError as exc:
                        print(f"ORDER_TRANSPORT_FAILURE reason={exc}")
                        if market is not None:
                            await market.close()
                        if time.monotonic() >= deadline:
                            break
                        await asyncio.sleep(1)
                        market = await connect_market()
                        trader.executor = PocketOptionDemoExecutor(market.client)
                        continue
                    print(
                        "ORDER_RESULT "
                        f"accepted={result.accepted} "
                        f"trade_id={result.trade_id} reason={result.reason}"
                    )
                    if result.accepted:
                        orders += 1
                        outcome_tracker.register(
                            trade_id=result.trade_id or f"accepted-{orders}",
                            asset=signal.asset,
                            direction=signal.direction,
                            amount=amount,
                            entry_price=selected_price,
                            expiration_seconds=expiration,
                        )

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
        print("OUTCOME_ESTIMATE_SUMMARY " + str(outcome_tracker.summary()))
        print("ASSET_EVALUATION_COUNTS " + str(dict(asset_evaluation_counts.most_common())))
        print("ASSET_DIRECTIONAL_CANDIDATES " + str(dict(asset_signal_counts.most_common())))
        print("DIRECTION_CANDIDATE_COUNTS " + str(dict(direction_candidate_counts.most_common())))
        print("SELECTED_ASSET_COUNTS " + str(dict(selected_asset_counts.most_common())))
        print("SELECTED_DIRECTION_COUNTS " + str(dict(selected_direction_counts.most_common())))
        print("REJECTION_REASON_COUNTS " + str(dict(rejection_counts.most_common())))
        print("DECISION_STAGE_COUNTS " + str(dict(decision_stage_counts.most_common())))
        if snapshots == 0:
            raise RuntimeError("No Demo market snapshots were received")
    finally:
        if market is not None:
            await market.close()


if __name__ == "__main__":
    asyncio.run(main())
