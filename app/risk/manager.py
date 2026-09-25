from app.core.models import Signal


class RiskManager:
    def __init__(self, max_daily_loss: float, max_consecutive_losses: int):
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.daily_pnl = 0.0
        self.consecutive_losses = 0

    def allowed(self, signal: Signal) -> bool:
        if self.daily_pnl <= -abs(self.max_daily_loss) and self.max_daily_loss > 0:
            return False
        return self.consecutive_losses < self.max_consecutive_losses

    def record_result(self, pnl: float) -> None:
        self.daily_pnl += pnl
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0
