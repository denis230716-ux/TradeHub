from app.core.pipeline import TradeHubPipeline


def test_pipeline_rejects_insufficient_history():
    pipeline = TradeHubPipeline()
    assert pipeline.evaluate("TEST", [100 + i for i in range(10)]) is None


def test_pipeline_returns_signal_or_hold_for_valid_history():
    prices = [100.0 + i * 0.15 for i in range(40)]
    volumes = [100.0] * len(prices)
    signal = TradeHubPipeline().evaluate("TEST", prices, volumes)
    assert signal is None or signal.direction in {"CALL", "PUT"}


def test_signal_generator_requires_minimum_predictor_confidence():
    from app.signals.generator import SignalGenerator

    generator = SignalGenerator()
    analysis = {
        "trend": 0.5,
        "momentum": 0.5,
        "rsi": 50.0,
        "prediction_change": 0.1,
        "prediction_confidence": 59.0,
        "near_support": False,
        "near_resistance": False,
    }

    assert generator.generate_signal("TEST", analysis).signal == "HOLD"

    analysis["prediction_confidence"] = 60.0
    assert generator.generate_signal("TEST", analysis).signal == "CALL"
