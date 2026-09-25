import asyncio
import json
import os

import websockets

WS_URL = os.environ.get(
    "POCKET_OPTION_WS_URL",
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
)
ORIGIN = os.environ.get("POCKET_OPTION_ORIGIN", "https://pocketoption.com")


def socket_event(name: str, *args: object) -> str:
    return "42" + json.dumps([name, *args], separators=(",", ":"))


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
        assets_seen = False
        idle_after_auth = 0
        for _ in range(40):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                if authenticated:
                    idle_after_auth += 1
                    if idle_after_auth >= 3:
                        break
                continue
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
            if message.startswith("42") and "updateAssets" in message:
                assets_seen = 1
            if authenticated and assets_seen:
                break

        if not authenticated:
            raise RuntimeError("Demo authentication confirmation was not received")

        asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
        period = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))

        # Verified community protocol uses changeSymbol + subfor.
        await ws.send(socket_event("changeSymbol", {"asset": asset, "period": period}))
        await ws.send(socket_event("subfor", asset))

        print(f"Subscribed to Demo market stream: {asset}, period={period}s")
        print("No trading commands are sent.")

        for _ in range(60):
            message = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(message, bytes):
                continue
            if message == "2":
                await ws.send("3")
                continue
            if message.startswith("451-"):
                try:
                    packet = json.loads(message.split("-", 1)[1])
                    event = str(packet[0]) if packet else ""
                    if event in {"updateStream", "updateHistoryNewFast", "updateCharts"}:
                        binary = await asyncio.wait_for(ws.recv(), timeout=10)
                        if isinstance(binary, bytes):
                            print(f"Realtime market event: {event}")
                            if event == "updateStream":
                                print("Realtime tick data: OK")
                            elif event == "updateHistoryNewFast":
                                print("Realtime history data: OK")
                            else:
                                print("Chart event: OK")
                            return
                except (json.JSONDecodeError, asyncio.TimeoutError):
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
            elif event == "updateStream":
                print("Realtime tick data: OK")
                return
            elif event == "updateHistoryNewFast":
                print("Realtime history data: OK")
                return
            elif event == "updateCharts":
                print("Chart event: OK")

        raise RuntimeError("Authenticated, but no realtime market event was received")


if __name__ == "__main__":
    asyncio.run(main())
