from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MarketUniverse:
    """Normalizes Pocket Option asset metadata into a tradable symbol list."""

    def __init__(self, assets: list[str] | None = None):
        self._assets = set(assets or [])

    @property
    def assets(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))

    def update(self, payload: Any) -> tuple[str, ...]:
        found: set[str] = set()
        self._collect(payload, found)
        self._assets.update(found)
        return self.assets

    def _collect(self, value: Any, found: set[str]) -> None:
        if isinstance(value, Mapping):
            for key in ("asset", "symbol", "ticker", "name", "pair"):
                candidate = value.get(key)
                if self._is_asset(candidate):
                    if self._tradable(value):
                        found.add(str(candidate))
            for key, child in value.items():
                if key not in {"asset", "symbol", "ticker", "name", "pair"}:
                    self._collect(child, found)
            return

        if isinstance(value, list):
            for item in value:
                self._collect(item, found)

    @staticmethod
    def _is_asset(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        value = value.strip()
        return bool(value) and len(value) <= 64 and any(ch.isalpha() for ch in value)

    @staticmethod
    def _tradable(value: Mapping[str, Any]) -> bool:
        for key in ("isActive", "active", "enabled", "tradable", "isTradable"):
            if key in value and value[key] is False:
                return False
        return True
