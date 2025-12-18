from dataclasses import dataclass


@dataclass
class TradingContext:
    """Context for kill switch checks."""

    portfolio: "Portfolio"
    config: "RiskConfig"
    broker_disconnected_seconds: float = 0


class KillSwitch:
    """Emergency halt."""

    def __init__(self):
        self.triggered = False
        self.reason = ""

    def check(self, context: TradingContext) -> bool:
        """Returns True if trading should halt."""
        if self.triggered:
            return True

        if context.portfolio.daily_pnl < -context.config.max_daily_loss:
            self.trigger("Daily loss limit exceeded")
            return True

        if context.broker_disconnected_seconds > 60:
            self.trigger("Broker connection lost")
            return True

        return False

    def trigger(self, reason: str):
        self.triggered = True
        self.reason = reason

    def reset(self):
        """Manual reset required after trigger."""
        self.triggered = False
        self.reason = ""

