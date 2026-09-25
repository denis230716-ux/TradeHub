from datetime import datetime, timezone

from app.core.models import Signal
from app.risk.manager import RiskManager
from app.strategy.indicators import calculate_momentum, calculate_rsi, calculate_sma
from app.strategy.market_analysis import MarketAnalysis
from app.strategy.scalping_guard import ScalpingGuard
from app.signals.generator import SignalGenerator


def test_indicators():
    prices = [1, 2, 3, 4, 5, 6]
    assert calculate_sma(prices, 3) == 5.0
    assert calculate_momentum(prices, 2) > 0
    assert calculate_rsi(prices, 3) == 100.0


def test_market_analysis():
    candles = [{"close": value, "volume": 100} for value in range(1, 25)]
    result = MarketAnalysis().analyze(candles)
    assert result.trading_allowed is True
    assert result.state == "UPTREND"


def test_scalping_guard():
    guard = ScalpingGuard(dry_run=True, dry_run_min_gross_profit_percent=0.1)
    assert guard.evaluate(0.2).allowed is True
    assert guard.evaluate(0.05).allowed is False


def test_signal_generator():
    generator = SignalGenerator()
    result = generator.generate_signal(
        "TEST",
        {"trend": 0.5, "momentum": 0.5, "rsi": 50},
    )
    assert result.signal == "CALL"


def test_risk_manager():
    manager = RiskManager(max_daily_loss=100, max_consecutive_losses=2)
    signal = Signal(
        asset="TEST",
        direction="CALL",
        confidence=90,
        timestamp=datetime.now(timezone.utc),
    )
    assert manager.allowed(signal)
    manager.record_result(-10)
    manager.record_result(-10)
    assert manager.allowed(signal) is False
