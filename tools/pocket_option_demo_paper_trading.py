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
            if signal is None:
                print(
                    f"DATA snapshots={snapshots} "
                    f"asset={snapshot.asset} price={snapshot.price} signal=HOLD"
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


if __name__ == "__main__":
    asyncio.run(main())
