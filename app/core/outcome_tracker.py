from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import monotonic


@dataclass(slots=True)
class PendingOutcome:
    trade_id: str
    asset: str
    direction: str
    amount: float
    entry_price: float
    expiration_seconds: int
    opened_at: float
    last_pre_expiry_price: float | None = None
    last_pre_expiry_at: float | None = None


class DemoOutcomeTracker:
    """Estimates outcomes from the first received quote after expiry.

    These are diagnostic estimates, not broker-confirmed settlements: actual
    expiry prices and asset-specific payouts may differ from the sampled quote
    and configured payout rate.
    """

    def __init__(self, payout_rate: float = 0.92) -> None:
        if not 0.0 <= payout_rate <= 1.0:
            raise ValueError("payout_rate must be between 0 and 1")
        self.payout_rate = float(payout_rate)
        self.pending: list[PendingOutcome] = []
        self.results: list[dict[str, object]] = []

    def register(
        self,
        *,
        trade_id: str,
        asset: str,
        direction: str,
        amount: float,
        entry_price: float,
        expiration_seconds: int,
        opened_at: float | None = None,
    ) -> None:
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        if amount <= 0 or entry_price <= 0 or expiration_seconds <= 0:
            raise ValueError("amount, entry price and expiry must be positive")
        self.pending.append(PendingOutcome(
            trade_id=trade_id,
            asset=asset,
            direction=direction,
            amount=float(amount),
            entry_price=float(entry_price),
            expiration_seconds=int(expiration_seconds),
            opened_at=monotonic() if opened_at is None else float(opened_at),
        ))

    def on_quote(
        self,
        asset: str,
        price: float,
        *,
        now: float | None = None,
    ) -> list[dict[str, object]]:
        current_time = monotonic() if now is None else float(now)
        settled: list[dict[str, object]] = []
        still_pending: list[PendingOutcome] = []
        for trade in self.pending:
            if trade.asset != asset:
                still_pending.append(trade)
                continue
            expiry_at = trade.opened_at + trade.expiration_seconds
            if current_time < expiry_at:
                trade.last_pre_expiry_price = float(price)
                trade.last_pre_expiry_at = current_time
                still_pending.append(trade)
                continue

            # Use the observed quote closest in time to expiry, rather than
            # always using the first quote after expiry. This remains an
            # estimate and cannot replace the broker's settlement record.
            expiry_price = float(price)
            quote_age = current_time - expiry_at
            quote_side = "after_expiry"
            if trade.last_pre_expiry_at is not None:
                before_age = expiry_at - trade.last_pre_expiry_at
                if before_age <= quote_age:
                    expiry_price = float(trade.last_pre_expiry_price)
                    quote_age = before_age
                    quote_side = "before_expiry"
            if expiry_price == trade.entry_price:
                outcome, net = "PUSH", 0.0
            else:
                won = (
                    expiry_price > trade.entry_price
                    if trade.direction == "CALL"
                    else expiry_price < trade.entry_price
                )
                outcome = "WIN" if won else "LOSS"
                net = trade.amount * self.payout_rate if won else -trade.amount
            result: dict[str, object] = {
                "trade_id": trade.trade_id,
                "asset": trade.asset,
                "direction": trade.direction,
                "amount": trade.amount,
                "entry_price": trade.entry_price,
                "sampled_expiry_price": expiry_price,
                "quote_side": quote_side,
                "quote_age_seconds": round(quote_age, 4),
                "expiration_seconds": trade.expiration_seconds,
                "outcome_estimate": outcome,
                "estimated_net": round(net, 8),
                "payout_rate_assumed": self.payout_rate,
                "settlement_source": "first_quote_after_expiry_NOT_broker_confirmed",
            }
            self.results.append(result)
            settled.append(result)
        self.pending = still_pending
        return settled

    def summary(self) -> dict[str, object]:
        wins = sum(item["outcome_estimate"] == "WIN" for item in self.results)
        losses = sum(item["outcome_estimate"] == "LOSS" for item in self.results)
        pushes = sum(item["outcome_estimate"] == "PUSH" for item in self.results)
        by_asset: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "losses": 0, "pushes": 0, "estimated_net": 0.0}
        )
        by_direction: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"trades": 0, "wins": 0, "losses": 0, "pushes": 0, "estimated_net": 0.0}
        )
        for item in self.results:
            for key, value in (("asset", str(item["asset"])), ("direction", str(item["direction"]))):
                group = by_asset[value] if key == "asset" else by_direction[value]
                group["trades"] += 1
                outcome_key = {"WIN": "wins", "LOSS": "losses", "PUSH": "pushes"}[str(item["outcome_estimate"])]
                group[outcome_key] += 1
                group["estimated_net"] = round(float(group["estimated_net"]) + float(item["estimated_net"]), 8)
        return {
            "settled_estimates": len(self.results),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "win_rate_excluding_pushes_percent": round(100 * wins / (wins + losses), 2) if wins + losses else None,
            "estimated_net": round(sum(float(item["estimated_net"]) for item in self.results), 8),
            "assumed_payout_rate": self.payout_rate,
            "break_even_win_rate_percent": round(
                100.0 / (1.0 + self.payout_rate), 2
            ),
            "pending": len(self.pending),
            "by_asset": dict(by_asset),
            "by_direction": dict(by_direction),
            "source": "ESTIMATES_ONLY_NOT_BROKER_SETTLEMENTS",
        }
