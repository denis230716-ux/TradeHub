from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re


@dataclass(frozen=True, slots=True)
class ExternalSignal:
    source: str
    asset: str
    direction: str
    confidence: float
    payout_percent: float
    expiration_seconds: int
    received_at: datetime


@dataclass(frozen=True, slots=True)
class SignalMatch:
    external: ExternalSignal
    tradehub_direction: str
    matched: bool
    reason: str


class PocketSignalsParser:
    """Parse the text format emitted by the PocketSignals Telegram bot."""

    _asset = re.compile(r"Актив:\s*#?([A-Za-z0-9_/-]+)", re.IGNORECASE)
    _payout = re.compile(r"Прибыльность по активу:\s*([0-9]+(?:[.,][0-9]+)?)%", re.IGNORECASE)
    _confidence = re.compile(r"Точность:\s*([0-9]+(?:[.,][0-9]+)?)%", re.IGNORECASE)
    _expiry = re.compile(r"Экспирация:\s*M([0-9]+)", re.IGNORECASE)

    @classmethod
    def parse(
        cls,
        text: str,
        received_at: datetime | None = None,
    ) -> ExternalSignal:
        if "СИГНАЛ" not in text.upper():
            raise ValueError("Message is not a signal")

        asset_match = cls._asset.search(text)
        payout_match = cls._payout.search(text)
        confidence_match = cls._confidence.search(text)
        expiry_match = cls._expiry.search(text)

        if not all((asset_match, payout_match, confidence_match, expiry_match)):
            raise ValueError("Signal message is missing required fields")

        direction = "CALL" if "СИГНАЛ ⬆" in text else "PUT" if "СИГНАЛ ⬇" in text else ""
        if not direction:
            raise ValueError("Signal direction is missing")

        expiry_minutes = int(expiry_match.group(1))
        return ExternalSignal(
            source="PocketSignals",
            asset=asset_match.group(1),
            direction=direction,
            confidence=float(confidence_match.group(1).replace(",", ".")),
            payout_percent=float(payout_match.group(1).replace(",", ".")),
            expiration_seconds=expiry_minutes * 60,
            received_at=received_at or datetime.now(timezone.utc),
        )


class ExternalSignalSynchronizer:
    """Keep external signals pending and match them to TradeHub decisions."""

    def __init__(
        self,
        min_confidence: float = 60.0,
        min_payout_percent: float = 80.0,
        max_age_seconds: int = 30,
    ) -> None:
        self.min_confidence = float(min_confidence)
        self.min_payout_percent = float(min_payout_percent)
        self.max_age_seconds = max(0, int(max_age_seconds))
        self._pending: dict[str, ExternalSignal] = {}

    def accept(self, signal: ExternalSignal) -> bool:
        if signal.confidence < self.min_confidence:
            return False
        if signal.payout_percent < self.min_payout_percent:
            return False
        self._pending[signal.asset] = signal
        return True

    def get(self, asset: str, now: datetime | None = None) -> ExternalSignal | None:
        signal = self._pending.get(asset)
        if signal is None:
            return None
        current = now or datetime.now(timezone.utc)
        age = (current - signal.received_at).total_seconds()
        if age < 0 or age > self.max_age_seconds:
            self._pending.pop(asset, None)
            return None
        return signal

    def compare(
        self,
        asset: str,
        tradehub_direction: str,
        now: datetime | None = None,
    ) -> SignalMatch | None:
        signal = self.get(asset, now=now)
        if signal is None:
            return None

        matched = signal.direction == tradehub_direction
        reason = (
            "external_and_tradehub_match"
            if matched
            else "external_and_tradehub_disagree"
        )
        return SignalMatch(
            external=signal,
            tradehub_direction=tradehub_direction,
            matched=matched,
            reason=reason,
        )

    def consume(self, asset: str) -> None:
        self._pending.pop(asset, None)
