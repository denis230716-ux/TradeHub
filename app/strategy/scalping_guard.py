from dataclasses import dataclass


@dataclass(slots=True)
class ScalpingDecision:
    allowed: bool
    reason: str
    estimated_net_profit_percent: float
    required_profit_percent: float


class ScalpingGuard:
    def __init__(
        self,
        commission_percent: float = 0.0,
        slippage_percent: float = 0.05,
        min_net_profit_percent: float = 0.10,
        safety_buffer_percent: float = 0.05,
        dry_run: bool = True,
        dry_run_min_gross_profit_percent: float = 0.10,
    ):
        self.commission_percent = max(0.0, float(commission_percent))
        self.slippage_percent = max(0.0, float(slippage_percent))
        self.min_net_profit_percent = max(0.0, float(min_net_profit_percent))
        self.safety_buffer_percent = max(0.0, float(safety_buffer_percent))
        self.dry_run = dry_run
        self.dry_run_min_gross_profit_percent = max(0.0, float(dry_run_min_gross_profit_percent))

    def required_profit_percent(self) -> float:
        return round(
            self.commission_percent * 2
            + self.slippage_percent * 2
            + self.min_net_profit_percent
            + self.safety_buffer_percent,
            10,
        )

    def required_entry_gross_profit_percent(self) -> float:
        if self.dry_run:
            return self.dry_run_min_gross_profit_percent
        return self.required_profit_percent()

    def evaluate(self, expected_move_percent: float) -> ScalpingDecision:
        required = self.required_entry_gross_profit_percent()
        expected = float(expected_move_percent)
        net = expected - (self.commission_percent * 2 + self.slippage_percent * 2)
        return ScalpingDecision(
            allowed=expected >= required,
            reason="expected movement accepted" if expected >= required else "expected movement below threshold",
            estimated_net_profit_percent=round(net, 6),
            required_profit_percent=round(required, 6),
        )
