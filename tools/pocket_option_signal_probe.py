from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from app.broker.pocket_option_socketio import PocketOptionSocketIO


def compact_signal(data: Any, depth: int = 0) -> dict[str, Any] | list[Any]:
    if isinstance(data, dict):
        fields = (
            "asset",
            "symbol",
            "direction",
            "action",
            "signal",
            "type",
            "confidence",
            "accuracy",
            "payout",
            "profitability",
            "expiration",
            "expiry",
            "time",
        )

        result = {
            key: data[key]
            for key in fields
            if key in data
        }

        nested_keys = ("signals", "times")
        if depth < 2:
            for key in nested_keys:
                if key in data:
                    result[key] = compact_signal(data[key], depth + 1)

        if result:
            return result

        return {
            "data_type": "dict",
            "keys": sorted(data),
        }

    if isinstance(data, list):
        sample = data[:8]
        if depth < 2:
            sample = [
                compact_signal(item, depth + 1)
                if isinstance(item, (dict, list))
                else item
                for item in sample
            ]

        return {
            "data_type": "list",
            "length": len(data),
            "sample": sample,
        }

    return {
        "data_type": type(data).__name__,
        "value": data,
    }


async def main() -> None:
    ssid = os.environ.get("POCKET_OPTION_SSID", "").strip()

    if not ssid:
        raise RuntimeError("POCKET_OPTION_SSID is required")

    timeout = float(
        os.environ.get(
            "POCKET_OPTION_SIGNAL_PROBE_TIMEOUT",
            "300",
        )
    )

    client = PocketOptionSocketIO(ssid)

    print("SIGNAL_PROBE mode=DEMO_ONLY orders=DISABLED")
    print(f"SIGNAL_PROBE timeout={timeout:g}s")

    await client.connect()

    try:
        print("SIGNAL_PROBE connected=true")

        await client.subscribe_signals()

        print('SIGNAL_PROBE subscribed="signals/subscribe"')

        deadline = time.monotonic() + timeout
        seen = 0

        while time.monotonic() < deadline:
            while seen < len(client.signal_updates):
                update = client.signal_updates[seen]
                seen += 1

                print(
                    "SIGNAL_EVENT "
                    + json.dumps(
                        {
                            "event": update.get("event"),
                            "data": compact_signal(update.get("data")),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )

            if client.disconnected.is_set():
                reason = client.disconnect_reason or "unknown"
                print(f"SIGNAL_PROBE_DISCONNECTED reason={reason}")
                if seen == 0:
                    raise RuntimeError(
                        f"WebSocket disconnected before any signal event: {reason}"
                    )
                break

            await asyncio.sleep(0.25)

        print(f"SIGNAL_PROBE_COMPLETED events={seen}")

        print(
            "SIGNAL_PROBE_EVENT_NAMES="
            + ",".join(client.events)
        )

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
