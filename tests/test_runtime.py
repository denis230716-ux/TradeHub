from app.core.config import settings
from app.core.pipeline import TradeHubPipeline
from app.execution.executor import DryRunExecutor
from app.main import build_runtime


def test_runtime_defaults_to_dry_run():
    runtime = build_runtime()
    assert runtime["dry_run"] is True
    assert runtime["risk"] is not None


def test_pipeline_is_deterministic_for_same_input():
    prices = [100.0 + i * 0.05 for i in range(50)]
    volumes = [100.0] * len(prices)

    first = TradeHubPipeline().evaluate("TEST", prices, volumes)
    second = TradeHubPipeline().evaluate("TEST", prices, volumes)

    assert (first is None) == (second is None)
    if first is not None and second is not None:
        assert first.direction == second.direction
        assert first.confidence == second.confidence


def test_dry_run_executor_never_submits_live_order():
    import asyncio

    async def run():
        executor = DryRunExecutor()
        return await executor.execute(
            __import__("app.core.models", fromlist=["TradeRequest"]).TradeRequest(
                asset="TEST",
                direction="CALL",
                amount=1.0,
                expiration_seconds=5,
            )
        )

    result = asyncio.run(run())
    assert result.accepted is True
    assert result.trade_id == "DRY_RUN"
    assert result.reason == "simulation"
