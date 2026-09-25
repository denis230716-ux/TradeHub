from __future__ import annotations
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass
class LearningStats:
    samples: int = 0
    wins: int = 0
    losses: int = 0
    pnl_sum: float = 0.0
    confidence_sum: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.samples if self.samples else 0.5

    @property
    def average_pnl(self) -> float:
        return self.pnl_sum / self.samples if self.samples else 0.0


class OnlineTradeLearner:
    VERSION = 1

    def __init__(self, storage_path: str = "data/ml_learning.json") -> None:
        self.storage_path = Path(storage_path)
        self.lock = RLock()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._global = LearningStats()
        self._by_key: dict[str, LearningStats] = {}
        self._processed: set[str] = set()
        self.load()

    @staticmethod
    def _key(symbol: str, action: str) -> str:
        return f"{str(symbol or '').upper().strip()}|{str(action or '').upper().strip()}"

    @staticmethod
    def _value(trade: Any, name: str, default: Any = None) -> Any:
        return trade.get(name, default) if isinstance(trade, dict) else getattr(trade, name, default)

    def _trade_id(self, trade: Any) -> str:
        fields = ("symbol", "action", "quantity", "entry_price", "exit_price", "closed_at")
        return "|".join(str(self._value(trade, field, "")) for field in fields)

    @staticmethod
    def _stats(value: dict[str, Any]) -> LearningStats:
        return LearningStats(
            samples=int(value.get("samples", 0)),
            wins=int(value.get("wins", 0)),
            losses=int(value.get("losses", 0)),
            pnl_sum=float(value.get("pnl_sum", 0)),
            confidence_sum=float(value.get("confidence_sum", 0)),
        )

    def load(self) -> None:
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return
        self._global = self._stats(data.get("global", {}))
        self._by_key = {
            key: self._stats(value)
            for key, value in data.get("by_key", {}).items()
            if isinstance(value, dict)
        }
        self._processed = set(data.get("processed", []))

    def save(self) -> None:
        payload = {
            "version": self.VERSION,
            "global": asdict(self._global),
            "by_key": {key: asdict(value) for key, value in self._by_key.items()},
            "processed": sorted(self._processed),
        }
        fd, temp_name = tempfile.mkstemp(prefix="ml_learning_", suffix=".tmp", dir=str(self.storage_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.storage_path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def learn_from_trade(self, trade: Any, confidence: float = 0.0) -> bool:
        trade_id = self._trade_id(trade)
        if not trade_id or trade_id in self._processed:
            return False
        try:
            pnl = float(self._value(trade, "net_pnl", 0) or 0)
            confidence = max(0, min(100, float(confidence or 0)))
        except (TypeError, ValueError):
            return False
        key = self._key(self._value(trade, "symbol", ""), self._value(trade, "action", ""))
        stats = self._by_key.setdefault(key, LearningStats())
        for bucket in (self._global, stats):
            bucket.samples += 1
            bucket.pnl_sum += pnl
            bucket.confidence_sum += confidence
            if pnl > 0:
                bucket.wins += 1
            elif pnl < 0:
                bucket.losses += 1
        self._processed.add(trade_id)
        self.save()
        return True

    def score_adjustment(self, symbol: str, action: str) -> float:
        stats = self._by_key.get(self._key(symbol, action), self._global)
        if stats.samples < 5:
            return 0.0
        edge = (stats.win_rate - 0.5) * 20
        pnl_edge = max(-5, min(5, stats.average_pnl))
        return max(-10, min(10, edge + pnl_edge))

    def snapshot(self) -> dict[str, Any]:
        return {
            "samples": self._global.samples,
            "wins": self._global.wins,
            "losses": self._global.losses,
            "win_rate": self._global.win_rate,
            "average_pnl": self._global.average_pnl,
        }
