from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from app.broker.pocket_option_socketio import PocketOptionSocketIO


def compact_signal(data: Any) -> dict[str, Any]:
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

        return result or {
            "data_type": "dict",
            "keys": sorted(data),
        }

    if isinstance(data, list):
        return {
            "data_type": "list",
            "length": len(data),
            "sample": data[:8],
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

    print("SIGNAL_PRO
