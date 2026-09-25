import asyncio
import os

import websockets


WS_URL = os.environ.get(
    "POCKET_OPTION_WS_URL",
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
)


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")
    if not ssid.startswith('42["auth",'):
        raise ValueError("POCKET_OPTION_SSID must be a complete auth frame")
    if '"isDemo":1' not in ssid:
        raise ValueError("POCKET_OPTION_SSID must be a Demo auth frame")

    async with websockets.connect(
        WS_URL,
        ping_interval=20,
        ping_timeout=10,
        open_timeout=15,
        close_timeout=5,
    ) as ws:
        first = await asyncio.wait_for(ws.recv(), timeout=10)
        if isinstance(first, bytes) or not str(first).startswith("0"):
            raise RuntimeError("Unexpected Engine.IO handshake")

        await ws.send("40")
        connected = await asyncio.wait_for(ws.recv(), timeout=10)
        if isinstance(connected, bytes) or not str(connected).startswith("40"):
            raise RuntimeError("Socket.IO connection was not established")

        await ws.send(ssid)

        for _ in range(20):
            message = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(message, bytes):
                continue
            if message == "2":
                await ws.send("3")
                continue
            if "successauth" in message:
                print("Pocket Option Demo authentication: OK")
                print("No trading command was sent.")
                return

        raise RuntimeError("Pocket Option Demo authentication was not confirmed")


if __name__ == "__main__":
    asyncio.run(main())
