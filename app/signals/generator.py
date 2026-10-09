from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(slots=True)
class SignalResult:
    symbol: str
    signal: str
    confidence: float
    score: float
    buy_score: float
    sell_score: float
    trend: float
    momentum: float
    rsi: float
    reasons: List[str]
    rejection_reasons: List[str]


class SignalGenerator:
    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        # 30 remains the strong-signal threshold. Near-threshold entries
        # require independent confirmation instead of simply lowering it.
        self.min_buy_score = float(config.get("min_buy_score", 30))
        self.min_buy_difference = float(config.get("min_buy_difference", 10))
        self.min_sell_score = float(config.get("min_sell_score", 30))
        self.near_threshold_score = float(config.get("near_threshold_score", 23))
        self.near_threshold_difference = float(
            config.get("near_threshold_difference", 4)
        )
        self.min_prediction_confidence = float(
            config.get("min_prediction_confidence", 55)
        )
        self.min_prediction_move_percent = float(
            config.get("min_prediction_move_percent", 0.01)
        )
        self.rsi_oversold = float(config.get("rsi_oversold", 35))
        self.rsi_overbought = float(config.get("rsi_overbought", 75))

    def generate_signal(self, symbol: str, analysis: Dict) -> SignalResult:
        buy = sell = 0.0
        reasons = []
        trend = float(analysis.get("trend", 0))
        momentum = float(analysis.get("momentum", 0))
        rsi = float(analysis.get("rsi", 50))
        prediction_confidence = float(
            analysis.get("prediction_confidence", 0)
        )
        prediction_change = float(analysis.get("prediction_change", 0))

        if trend >= 0.30:
            buy += 15
            reasons.append("strong uptrend")
        elif trend >= 0.10:
            buy += 10
        elif trend > 0:
            buy += 5
        elif trend <= -0.30:
            sell += 15
            reasons.append("strong downtrend")
        elif trend < 0:
            sell += 5

        if momentum >= 0.30:
            buy += 12
            reasons.append("strong momentum")
        elif momentum >= 0.10:
            buy += 8
        elif momentum > 0:
            buy += 4
        elif momentum <= -0.30:
            sell += 12
        elif momentum < 0:
            sell += 4

        if rsi <= self.rsi_oversold:
            buy += 15
            reasons.append("oversold")
        elif rsi >= self.rsi_overbought:
            sell += 15
            reasons.append("overbought")

        if analysis.get("near_support"):
            buy += 8
        if analysis.get("near_resistance"):
            sell += 8

        difference = buy - sell
        strong_call = (
            buy >= self.min_buy_score
            and difference >= self.min_buy_difference
        )
        strong_put = (
            sell >= self.min_sell_score
            and difference <= -self.min_buy_difference
        )

        # Scores in the 25-29 range were common in test #13. They are not
        # promoted to trades by score alone: a near-threshold signal must
        # agree with the market direction and have an independent predictor
        # confidence confirmation.
        near_call = (
            buy >= self.near_threshold_score
            and difference >= self.near_threshold_difference
            and trend > 0
            and momentum > 0
            and prediction_confidence >= self.min_prediction_confidence
            and not analysis.get("near_resistance", False)
        )
        near_put = (
            sell >= self.near_threshold_score
            and difference <= -self.near_threshold_difference
            and trend < 0
            and momentum < 0
            and prediction_confidence >= self.min_prediction_confidence
            and not analysis.get("near_support", False)
        )

        prediction_direction_is_meaningful = (
            abs(prediction_change) >= self.min_prediction_move_percent
        )
        prediction_bullish = prediction_direction_is_meaningful and prediction_change > 0
        prediction_bearish = prediction_direction_is_meaningful and prediction_change < 0

        # A score is not enough: the independent predictor must point in the
        # same direction. This prevents CALL/PUT entries against the forecast.
        if prediction_direction_is_meaningful:
            if strong_call and not prediction_bullish:
                strong_call = False
            if strong_put and not prediction_bearish:
                strong_put = False
            if near_call and not prediction_bullish:
                near_call = False
            if near_put and not prediction_bearish:
                near_put = False

        rejection_reasons: List[str] = []
        if not (strong_call or near_call or strong_put or near_put):
            if buy >= self.near_threshold_score:
                if difference < self.near_threshold_difference:
                    rejection_reasons.append("CALL_SCORE_DIFFERENCE_TOO_SMALL")
                if trend <= 0:
                    rejection_reasons.append("CALL_TREND_NOT_BULLISH")
                if momentum <= 0:
                    rejection_reasons.append("CALL_MOMENTUM_NOT_BULLISH")
                if prediction_confidence < self.min_prediction_confidence:
                    rejection_reasons.append("CALL_PREDICTION_CONFIDENCE_LOW")
                if analysis.get("near_resistance", False):
                    rejection_reasons.append("CALL_NEAR_RESISTANCE")
                if prediction_direction_is_meaningful and not prediction_bullish:
                    rejection_reasons.append("CALL_PREDICTOR_DIRECTION_CONFLICT")
            if sell >= self.near_threshold_score:
                if difference > -self.near_threshold_difference:
                    rejection_reasons.append("PUT_SCORE_DIFFERENCE_TOO_SMALL")
                if trend >= 0:
                    rejection_reasons.append("PUT_TREND_NOT_BEARISH")
                if momentum >= 0:
                    rejection_reasons.append("PUT_MOMENTUM_NOT_BEARISH")
                if prediction_confidence < self.min_prediction_confidence:
                    rejection_reasons.append("PUT_PREDICTION_CONFIDENCE_LOW")
                if analysis.get("near_support", False):
                    rejection_reasons.append("PUT_NEAR_SUPPORT")
                if prediction_direction_is_meaningful and not prediction_bearish:
                    rejection_reasons.append("PUT_PREDICTOR_DIRECTION_CONFLICT")
            if not rejection_reasons:
                rejection_reasons.append("SCORE_BELOW_ENTRY_THRESHOLD")
            signal = "HOLD"
        elif strong_call or near_call:
            signal = "CALL"
            if near_call and not strong_call:
                reasons.append("near-threshold confirmed by trend/momentum/predictor")
        else:
            signal = "PUT"
            if near_put and not strong_put:
                reasons.append("near-threshold confirmed by trend/momentum/predictor")

        total = max(buy, sell)
        confidence = min(100.0, total)
        return SignalResult(
            symbol,
            signal,
            confidence,
            total,
            buy,
            sell,
            trend,
            momentum,
            rsi,
            reasons,
            rejection_reasons,
        )
