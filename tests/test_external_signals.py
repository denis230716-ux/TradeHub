from datetime import datetime, timezone, timedelta

import pytest

from app.external_signals.pocket_signals import (
    ExternalSignalSynchronizer,
    PocketSignalsParser,
)


def test_parse_call_signal():
    signal = PocketSignalsParser.parse(
        """СИГНАЛ ⬆
Актив: #CSCO_otc
Прибыльность по активу: 86%
Точность: 64%
Экспирация: M5""",
        received_at=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc),
    )

    assert signal.asset == "CSCO_otc"
    assert signal.direction == "CALL"
    assert signal.confidence == 64
    assert signal.payout_percent == 86
    assert signal.expiration_seconds == 300


def test_parse_put_signal():
    signal = PocketSignalsParser.parse(
        """СИГНАЛ ⬇
Актив: XAGUSD_otc
Прибыльность по активу: 80%
Точность: 67%
Экспирация: M5"""
    )
    assert signal.direction == "PUT"


def test_reject_low_quality_signal():
    synchronizer = ExternalSignalSynchronizer()
    signal = PocketSignalsParser.parse(
        """СИГНАЛ ⬆
Актив: #CSCO_otc
Прибыльность по активу: 79%
Точность: 64%
Экспирация: M5"""
    )
    assert synchronizer.accept(signal) is False


def test_match_and_disagreement():
    synchronizer = ExternalSignalSynchronizer(max_age_seconds=30)
    received = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    signal = PocketSignalsParser.parse(
        """СИГНАЛ ⬆
Актив: #CSCO_otc
Прибыльность по активу: 86%
Точность: 64%
Экспирация: M5""",
        received_at=received,
    )
    assert synchronizer.accept(signal)

    match = synchronizer.compare(
        "CSCO_otc",
        "CALL",
        now=received + timedelta(seconds=10),
    )
    assert match is not None
    assert match.matched is True

    mismatch = synchronizer.compare(
        "CSCO_otc",
        "PUT",
        now=received + timedelta(seconds=10),
    )
    assert mismatch is not None
    assert mismatch.matched is False


def test_expired_signal_is_not_used():
    synchronizer = ExternalSignalSynchronizer(max_age_seconds=30)
    received = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    signal = PocketSignalsParser.parse(
        """СИГНАЛ ⬇
Актив: XAGUSD_otc
Прибыльность по активу: 80%
Точность: 67%
Экспирация: M5""",
        received_at=received,
    )
    assert synchronizer.accept(signal)
    assert synchronizer.get(
        "XAGUSD_otc",
        now=received + timedelta(seconds=31),
    ) is None
