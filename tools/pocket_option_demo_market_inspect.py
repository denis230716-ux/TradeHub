import asyncio
import json
import os

import websockets

WS_URL = os.environ.get(
    "POCKET_OPTION_WS_URL",
    "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
)
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
        ping_timeout=20,
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

        for _ in range(40):
            message = await asyncio.wait_for(ws.recv(), timeout=5)
            if isinstance(message, bytes):
                continue
            if message == "2":
                await ws.send("3")
                continue
            if "successauth" in message:
                authenticated = True
                break
            if message.startswith("41"):
                raise RuntimeError("Pocket Option rejected Demo authentication")
            if message.startswith("451-"):
                packet = json.loads(message.split("-", 1)[1])
                if packet and packet[0] == "updateAssets":
                    binary = await asyncio.wait_for(ws.recv(), timeout=10)
                    if isinstance(binary, bytes):
                        continue

        if not authenticated:
            raise RuntimeError("Demo authentication confirmation was not received")

        asset = os.environ.get("POCKET_OPTION_ASSET", "EURJPY_otc")
        period = int(os.environ.get("POCKET_OPTION_PERIOD", "5"))
        await ws.send("42" + json.dumps(
            ["changeSymbol", {"asset": asset, "period": period}],
            separators=(",", ":"),
        ))
        await ws.send("42" + json.dumps(["subscribeSymbol", asset], separators=(",", ":")))
        await ws.send("42" + json.dumps(["subfor", asset], separators=(",", ":")))

        print(f"Subscribed: {asset}; period={period}s")
        print("Inspecting payload structure only; no trading commands are sent.")

        for _ in range(80):
            message = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(message, bytes):
                continue
            if message == "2":
                await ws.send("3")
                continue

            if message.startswith("451-"):
                packet = json.loads(message.split("-", 1)[1])
                if not packet:
                    continue
                event = str(packet[0])
                if event not in {"updateStream", "updateHistoryNewFast", "updateCharts"}:
                    continue

                payload = await asyncio.wait_for(ws.recv(), timeout=10)
                if isinstance(payload, bytes):
                    try:
                        data = json.loads(payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        data = {"type": "bytes", "length": len(payload)}
                else:
                    try:
                        data = json.loads(str(payload))
                    except json.JSONDecodeError:
                        data = str(payload)

                print(f"EVENT={event}")
                print(f"DATA_TYPE={type(data).__name__}")
                if isinstance(data, list):
                    print(f"DATA_LEN={len(data)}")
                    if data:
                        print(f"FIRST_TYPE={type(data[0]).__name__}")
                        print(f"FIRST_VALUE={json.dumps(data[0], ensure_ascii=False)[:2000]}")
                elif isinstance(data, dict):
                    print(f"DATA_KEYS={sorted(map(str, data.keys()))[:50]}")
                    print(f"DATA_SAMPLE={json.dumps(data, ensure_ascii=False)[:2000]}")
                else:
                    print(f"DATA_SAMPLE={str(data)[:2000]}")
                return

            if message.startswith("42"):
                try:
                    packet = json.loads(message[2:])
                except json.JSONDecodeError:
                    continue
                if not isinstance(packet, list) or not packet:
                    continue
                event = str(packet[0])
                if event not in {"updateStream", "updateHistoryNewFast", "updateCharts"}:
                    continue
                data = packet[1] if len(packet) > 1 else None
                print(f"EVENT={event}")
                print(f"DATA_TYPE={type(data).__name__}")
                if isinstance(data, list):
                    print(f"DATA_LEN={len(data)}")
                    if data:
                        print(f"FIRST_TYPE={type(data[0]).__name__}")
                        print(f"FIRST_VALUE={json.dumps(data[0], ensure_ascii=False)[:2000]}")
                elif isinstance(data, dict):
                    print(f"DATA_KEYS={sorted(map(str, data.keys()))[:50]}")
                    print(f"DATA_SAMPLE={json.dumps(data, ensure_ascii=False)[:2000]}")
                else:
                    print(f"DATA_SAMPLE={str(data)[:2000]}")
                return

        raise RuntimeError("Authenticated, but no inspectable realtime market event was received.")


if __name__ == "__main__":
    asyncio.run(main())
