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


def decode_event(message):
    if not isinstance(message, str) or not message.startswith("42"):
        return None
    try:
        payload = json.loads(message[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    return str(payload[0]), payload[1:]


def decode_binary_payload(message):
    if not isinstance(message, bytes):
        return None
    try:
        text = message.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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
        pending_binary_event = None
        asset_event_seen = False

        for _ in range(80):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                if authenticated:
                    continue
                raise

            if isinstance(message, bytes):
                if pending_binary_event == "updateAssets":
                    payload = decode_binary_payload(message)
                    if payload is not None:
                        universe.update(payload)
                        asset_event_seen = bool(universe.assets)
                    pending_binary_event = None
                continue

            if message == "2":
                await ws.send("3")
                continue
            if message.startswith("41"):
                raise RuntimeError("Pocket Option rejected Demo authentication")

            if "successauth" in message:
                authenticated = True
                print("Demo authentication: OK")

            if message.startswith('451-'):
                try:
                    header = json.loads(message.split("-", 1)[1])
                    event = str(header[0]) if header else ""
                    if event == "updateAssets":
                        pending_binary_event = event
                except json.JSONDecodeError:
                    pending_binary_event = None
                continue

            decoded = decode_event(message)
            if decoded and decoded[0] == "updateAssets":
                asset_event_seen = True
                for payload in decoded[1]:
                    universe.update(payload)

            if asset_event_seen and universe.assets:
                break

        if not authenticated:
            raise RuntimeError("Demo authentication confirmation was not received")
        if not universe.assets:
            raise RuntimeError(
                "Authenticated, but the Pocket Option asset catalog was not decoded. "
                "The server sent no directly parseable updateAssets payload."
            )

        print(f"Market universe discovery: OK ({len(universe.assets)} assets)")
        print("Assets: " + ", ".join(universe.assets[:50]))
        print("No trading commands are sent.")


if __name__ == "__main__":
    asyncio.run(main())
