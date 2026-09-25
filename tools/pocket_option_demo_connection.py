import asyncio
import os

import websockets


WS_URLS = [
    os.environ.get(
        "POCKET_OPTION_WS_URL",
        "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    ),
    "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
]
ORIGIN = os.environ.get("POCKET_OPTION_ORIGIN", "https://pocketoption.com")


async def check_url(url: str, ssid: str) -> bool:
    print(f"Connecting to {url.split('/socket.io')[0]} ...")
    try:
        async with websockets.connect(
            url,
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

            for _ in range(20):
                message = await asyncio.wait_for(ws.recv(), timeout=10)
                if isinstance(message, bytes):
                    continue
                if message == "2":
                    await ws.send("3")
                    continue
                if message.startswith("41"):
                    raise RuntimeError("Pocket Option rejected the Demo authentication")
                if "successauth" in message:
                    print("Pocket Option Demo authentication: OK")
                    print("No trading command was sent.")
                    return True

            raise RuntimeError("authentication confirmation was not received")
    except Exception as exc:
        print(f"Connection attempt failed: {type(exc).__name__}: {exc}")
        return False


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()
    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID secret is not configured")
    if not ssid.startswith('42["auth",'):
        raise ValueError("POCKET_OPTION_SSID must be a complete auth frame")
    if '"isDemo":1' not in ssid:
        raise ValueError("POCKET_OPTION_SSID must be a Demo auth frame")

    for url in dict.fromkeys(WS_URLS):
        if await check_url(url, ssid):
            return

    raise RuntimeError(
        "Pocket Option Demo connection was not established on the available Demo endpoints"
    )


if __name__ == "__main__":
    asyncio.run(main())
