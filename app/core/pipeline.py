from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.models import MarketSnapshot, Signal
from app.ml.predictor import MarketPredictor
from app.risk.manager import RiskManager
from app.signals.generator import SignalGenerator
from app.strategy.indicators import calculate_momentum, calculate_rsi
from app.strategy.market_analysis import MarketAnalysis
from app.strategy.scalping_guard import ScalpingGuard


class TradeHubPipeline:
    """Deterministic dry-run decision pipeline."""

    def __init__(
        self,
        predictor: MarketPredictor | None = None,
        market_analysis: MarketAnalysis | None = None,
        signal_generator: SignalGenerator | None = None,
        scalping_guard: ScalpingGuard | None = None,
        risk_manager: RiskManager | None = None,
    ):
        self.predictor = predictor or MarketPredictor()
        self.market_analysis = market_analysis or MarketAnalysis()
        self.signal_generator = signal_generator or SignalGenerator()
        self.scalping_guard = scalping_guard or ScalpingGuard(dry_run=True)
        self.risk_manager = risk_manager or RiskManager(
            max_daily_loss=0,
            max_consecutive_losses=3,
        )
        self.last_diagnostics: dict[str, float | str | bool] = {}

    def evaluate(
        self,
        asset: str,
        prices: list[float],
        volumes: list[float] | None = None,
        candles: list[dict[str, Any]] | None = None,
    ) -> Signal | None:
        if candles is None:
            if len(prices) < 21:
                self.last_diagnostics = {"decision_stage": "INSUFFICIENT_HISTORY"}
                return None
            volumes = volumes or [0.0] * len(prices)
            candles = [
                {"close": price, "volume": volume}
                for price, volume in zip(prices, volumes)
            ]
        elif len(candles) < 21:
            self.last_diagnostics = {"decision_stage": "INSUFFICIENT_HISTORY"}
            return None
        else:
            prices = [float(candle["close"]) for candle in candles]
            volumes = [float(candle.get("volume", 0.0)) for candle in candles]

        market = self.market_analysis.analyze(candles)
        if not market.trading_allowed:
            self.last_diagnostics = {
                "decision_stage": "MARKET_BLOCKED",
                "market_state": market.state,
                "market_volatility": market.volatility_percent,
                "trading_allowed": market.trading_allowed,
            }
            return None

        prediction = self.predictor.predict(asset, prices)
        current = prediction.current_price
        prediction_change = (
            (prediction.predicted_price - current) / current * 100
            if current > 0 else 0.0
        )

        analysis = {
            "trend": market.trend_percent,
            "momentum": calculate_momentum(prices, 5) or 0.0,
            "rsi": calculate_rsi(prices, 14) or 50.0,
            "near_support": market.near_support,
            "near_resistance": market.near_resistance,
            "prediction_change": prediction_change,
            "prediction_confidence": prediction.confidence,
        }
        generated = self.signal_generator.generate_signal(asset, analysis)
        self.last_diagnostics = {
            **analysis,
            "decision_stage": (
                "GENERATOR_HOLD"
                if generated.signal == "HOLD"
                else "SIGNAL_GENERATED"
            ),
            "market_state": market.state,
            "market_volatility": market.volatility_percent,
            "trading_allowed": market.trading_allowed,
            "buy_score": generated.buy_score,
            "sell_score": generated.sell_score,
            "signal": generated.signal,
            "signal_confidence": generated.confidence,
            "signal_rejection_reasons": ",".join(
                generated.rejection_reasons
            ),
        }

        if generated.signal == "HOLD":
            return None

        self.last_diagnostics["scalping_guard"] = (
            "not_applicable_binary_option"
        )

        signal = Signal(
            asset=asset,
            direction=generated.signal,
            confidence=generated.confidence,
            timestamp=datetime.now(timezone.utc),
            reason="; ".join(generated.reasons),
        )
        risk_allowed = self.risk_manager.allowed(signal)
        self.last_diagnostics["risk_allowed"] = risk_allowed
        if not risk_allowed:
            self.last_diagnostics["decision_stage"] = "RISK_BLOCKED"
            return None

        self.last_diagnostics["decision_stage"] = "SIGNAL_READY"
        return signal
