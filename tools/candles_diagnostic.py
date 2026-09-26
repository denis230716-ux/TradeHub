from __future__ import annotations

import asyncio
import os
import pprint

from app.market.market_data import PocketOptionMarketData


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
    timeout = float(os.environ.get("POCKET_OPTION_CANDLES_TIMEOUT", "20"))

    market = PocketOptionMarketData(session=ssid)

    if market.client is None:
        raise RuntimeError("Pocket Option transport is not initialized")

    try:
        await market.connect()
        await market.subscribe(asset, period=5)

        print(f"CANDLES_DIAGNOSTIC_START asset={asset}")
        print("MODE=DEMO_ONLY LIVE_TRADING_BLOCKED")

        deadline = asyncio.get_running_loop().time() + timeout
        history_index = 0

        while asyncio.get_running_loop().time() < deadline:
            while history_index < len(market.client.history_updates):
                update = market.client.history_updates[history_index]
                history_index += 1

                if not isinstance(update, dict):
                    continue

                candles = update.get("candles")

                print(
                    "HISTORY_PAYLOAD "
                    f"asset={update.get('asset')} "
                    f"period={update.get('period')} "
                    f"history_rows="
                    f"{len(update.get('history', [])) if isinstance(update.get('history'), list) else 0}"
                )

                print(f"CANDLES_TYPE={type(candles).__name__}")
                print("CANDLES_VALUE=")
                pprint.pprint(candles, sort_dicts=False)

                print("CANDLES_DIAGNOSTIC_COMPLETED")
                return

            if market.client.disconnected.is_set():
                break

            await asyncio.sleep(0.1)

        raise RuntimeError(
            "No updateHistoryNewFast payload with candles received"
        )

    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
