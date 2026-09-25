from dataclasses import dataclass


@dataclass(slots=True)
class HealthState:
    running: bool = False
    last_market_update: float | None = None
    last_signal: float | None = None
    last_trade: float | None = None
