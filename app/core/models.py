from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MarketSnapshot:
    asset: str
    price: float
    timestamp: datetime
    features: dict[str, Any]


@dataclass(slots=True)
class Signal:
    asset: str
    direction: str
    confidence: float
    timestamp: datetime
    reason: str = ""


@dataclass(slots=True)
class TradeRequest:
    asset: str
    direction: str
    amount: float
    expiration_seconds: int


@dataclass(slots=True)
class TradeResult:
    accepted: bool
    trade_id: str | None = None
    reason: str = ""
