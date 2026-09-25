import asyncio
import json
import os

import websockets

from app.market.universe import MarketUniverse

WS_URL = os.environ.get(
    "POCKET_OPTION_WS_URL",
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
)
ORIGIN = os.environ.get("POCKET_OPTION_ORIGIN", "https://pocketoption.com")


def decode_event(message: str):
    if not message.startswith("42"):
        return None
    try:
        payload = json.loads(message[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    return str(payload[0]), payload[1:]


async def main():
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")
    if not ssid.startswith('42["auth",') or '"isDemo":1' not in ssid:
        raise ValueError("POCKET_OPTION_SSID must be a complete Demo auth frame")

    universe = MarketUniverse()

    async with websockets.connect(
        WS_URL,
        additional_headers={"Origin": ORIGIN},
        ping_interval=20,
        ping_timeout=10,
        open_timeout=15,
        close_timeout=5,
    ) as ws:
        first = await asyncio.wait_for(ws.recv(), timeout=10)
        if isinstance(first, bytes) or not str(first).startswith("0"):
            raise RuntimeError("unexpected Engine.IO handshake")

        await ws.send("40")
        connected = await asyncio.wait_for(ws.recv(), timeout=10)
        if isinstance(connected, bytes) or not str(connected).startswith("40"):
            raise RuntimeError("Socket.IO connection was not established")

        await ws.send(ssid)

        authenticated = False
        assets_seen = False

        for _ in range(40):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                if authenticated:
                    continue
                raise

            if isinstance(message, bytes):
                continue
            if message == "2":
                await ws.send("3")
                continue
            if message.startswith("41"):
                raise RuntimeError("Pocket Option rejected Demo authentication")
            if "successauth" in message:
                authenticated = True
                print("Demo authentication: OK")

            decoded = decode_event(message)
            if decoded and decoded[0] == "updateAssets":
                assets_seen = True
                for payload in decoded[1]:
                    universe.update(payload)
                break

        if not authenticated:
            raise RuntimeError("Demo authentication confirmation was not received")
        if not assets_seen or not universe.assets:
            raise RuntimeError("Authenticated, but no tradable asset universe was received")

        print(f"Market universe discovery: OK ({len(universe.assets)} assets)")
        print("Assets: " + ", ".join(universe.assets[:50]))
        print("No trading commands are sent.")


if __name__ == "__main__":
    asyncio.run(main())
