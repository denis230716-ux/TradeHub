from datetime import datetime, timezone

from app.core.config import settings
from app.core.models import Signal
from app.risk.manager import RiskManager


def test_dry_run_default():
    assert settings.dry_run is True


def test_risk_manager_allows_initial_signal():
    manager = RiskManager(max_daily_loss=100, max_consecutive_losses=3)
    signal = Signal(
        asset="TEST",
        direction="CALL",
        confidence=0.9,
        timestamp=datetime.now(timezone.utc),
    )
    assert manager.allowed(signal)
