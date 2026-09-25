from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    dry_run: bool = True
    log_level: str = "INFO"

    pocket_option_session: str | None = None
    pocket_option_token: str | None = None

    default_asset: str | None = None
    timeframe_seconds: int = 5
    trade_amount: float = 1.0
    max_daily_loss: float = 0.0
    max_consecutive_losses: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
