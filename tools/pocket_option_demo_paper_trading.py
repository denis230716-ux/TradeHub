from __future__ import annotations

import asyncio
import os

from app.core.paper_trader import DemoPaperTrader
from app.market.market_data import PocketOptionMarketData


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
    period = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
    timeout = float(os.environ.get("POCKET_OPTION_PAPER_TIMEOUT", "30"))

    market = PocketOptionMarketData(session=ssid)
    trader = DemoPaperTrader(amount=1.0, expiration_seconds=period)

    try:
        await market.connect()
        await market.subscribe(asset, period=period)
        print(f"Demo paper trading: {asset}; period={period}s")
        print("Real orders are disabled.")

        snapshots = 0
        async for snapshot in market.stream(timeout=timeout):
            trader.ingest(snapshot)
            snapshots += 1

            if snapshots % 20 != 0:
                continue

            signal = trader.evaluate()
            diagnostics = trader.pipeline.last_diagnostics
            if signal is None:
                print(
                    f"DATA snapshots={snapshots} asset={snapshot.asset} "
                    f"price={snapshot.price} signal=HOLD "
                    f"state={diagnostics.get('market_state', 'n/a')} "
                    f"trend={float(diagnostics.get('trend', 0.0)):.4f} "
                    f"momentum={float(diagnostics.get('momentum', 0.0)):.4f} "
                    f"rsi={float(diagnostics.get('rsi', 50.0)):.2f} "
                    f"pred={float(diagnostics.get('prediction_change', 0.0)):.4f} "
                    f"buy={float(diagnostics.get('buy_score', 0.0)):.1f} "
                    f"sell={float(diagnostics.get('sell_score', 0.0)):.1f} "
                    f"allowed={diagnostics.get('trading_allowed', False)}"
                )
                continue

            result = await trader.open_virtual_trade(signal, snapshot.price)
            print(
                f"DATA snapshots={snapshots} asset={snapshot.asset} "
                f"price={snapshot.price} signal={signal.direction} "
                f"confidence={signal.confidence:.1f} "
                f"accepted={result.accepted} trade_id={result.trade_id}"
            )

        if snapshots == 0:
            raise RuntimeError("No Demo market snapshots were received")

        print(f"Paper trading completed: snapshots={snapshots}")
    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
