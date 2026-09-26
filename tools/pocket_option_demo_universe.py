import asyncio
import os

from app.broker.pocket_option_socketio import PocketOptionSocketIO
from app.market.universe import MarketUniverse


async def main():
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")

    client = PocketOptionSocketIO(ssid)
    universe = MarketUniverse()

    try:
        await client.connect()
        print("Demo authentication: OK")

        assets = await client.wait_for_assets(timeout=20)
        for asset in assets:
            universe.update(asset)

        if not universe.assets:
            observed = ", ".join(client.events[:30]) or "none"
            raise RuntimeError(
                "Demo authentication succeeded, but no asset catalog was decoded. "
                f"Observed events: {observed}"
            )

        print(f"Market universe discovery: OK ({len(universe.assets)} assets)")
        print("Assets: " + ", ".join(universe.assets[:50]))
        print("Observed events: " + ", ".join(client.events[:30]))
        print("No trading commands are sent.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
