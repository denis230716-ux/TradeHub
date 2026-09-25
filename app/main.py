from app.core.config import settings
from app.risk.manager import RiskManager


def build_runtime() -> dict:
    return {
        "environment": settings.app_env,
        "dry_run": settings.dry_run,
        "risk": RiskManager(
            max_daily_loss=settings.max_daily_loss,
            max_consecutive_losses=settings.max_consecutive_losses,
        ),
    }


if __name__ == "__main__":
    runtime = build_runtime()
    print(
        f"TradeHub started: env={runtime['environment']} "
        f"dry_run={runtime['dry_run']}"
    )
