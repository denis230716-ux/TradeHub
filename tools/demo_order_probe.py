from __future__ import annotations

import asyncio
import os

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

    market = PocketOptionMarketData(
        session=ssid
    )

    if market.client is None:
        raise RuntimeError(
            "Pocket Option transport is not initialized"
        )

    try:
        await market.connect()

        await market.subscribe(
            asset,
            period=expiration,
        )

        snapshot = None

        async for item in market.stream(
            timeout=10
        ):
            snapshot = item
            break

        if snapshot is None:
            raise RuntimeError(
                "No Demo market price received"
            )

        print(
            f"ORDER_TEST "
            f"price={snapshot.price} "
            f"asset={snapshot.asset} "
            f"amount={amount} "
            f"direction=CALL "
            f"expiration={expiration}s"
        )

        print(
            "LIVE trading is blocked. "
            "Demo session only."
        )

        result = await market.client.open_order(
            asset=asset,
            amount=amount,
            direction="CALL",
            expiration_seconds=expiration,
        )

        print(
            f"OPEN_ORDER_RESPONSE={result!r}"
        )

    finally:
        await market.close()


if __name__ == "__main__":
    asyncio.run(main())
