import asyncio
import json
import os

import websockets

WS_URL = os.environ.get("POCKET_OPTION_WS_URL", "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket")
ORIGIN = os.environ.get("POCKET_OPTION_ORIGIN", "https://pocketoption.com")


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")
    if not ssid.startswith('42["auth",') or '"isDemo":1' not in ssid:
        raise ValueError("POCKET_OPTION_SSID must be a complete Demo auth frame")

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
        for _ in range(30):
            message = await asyncio.wait_for(ws.recv(), timeout=10)
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
                break

        if not authenticated:
            raise RuntimeError("Demo authentication confirmation was not received")

        print("Listening for Demo market events; no trading commands are sent.")
        for _ in range(30):
            message = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(message, bytes):
                continue
            if message == "2":
                await ws.send("3")
                continue
            if not message.startswith("42"):
                continue
            try:
                payload = json.loads(message[2:])
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, list) or not payload:
                continue
            event = str(payload[0])
            if event == "updateAssets":
                print("Market event: updateAssets")
            elif event == "updateCharts":
                print("Market event: updateCharts")
                print("Realtime chart data: OK")
                return
            elif event == "updateBalance":
                print("Demo balance event: OK")

        raise RuntimeError("Authenticated, but no realtime chart event was received")


if __name__ == "__main__":
    asyncio.run(main())
