from app.core.pipeline import TradeHubPipeline


def test_pipeline_rejects_insufficient_history():
    pipeline = TradeHubPipeline()
    assert pipeline.evaluate("TEST", [100 + i for i in range(10)]) is None


def test_pipeline_returns_signal_or_hold_for_valid_history():
    prices = [100.0 + i * 0.15 for i in range(40)]
    volumes = [100.0] * len(prices)
    signal = TradeHubPipeline().evaluate("TEST", prices, volumes)
    assert signal is None or signal.direction in {"CALL", "PUT"}
