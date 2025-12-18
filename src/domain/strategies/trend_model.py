from typing import Optional
from decimal import Decimal
from datetime import datetime

from .base import TradingStrategy
from ..events.signal import Signal


class TrendModel(TradingStrategy):
    """Momentum/trend following."""

    def __init__(self, lookback: int = 20, threshold: float = 0.02):
        self.lookback = lookback
        self.threshold = threshold
        self.price_history: list = []

    def generate_signal(
        self,
        market_state: "MarketState",
        portfolio: "Portfolio",
    ) -> Optional[Signal]:
        self.price_history.append(float(market_state.mid))
        if len(self.price_history) > self.lookback:
            self.price_history.pop(0)

        if len(self.price_history) < self.lookback:
            return None

        returns = (self.price_history[-1] / self.price_history[0]) - 1
        if abs(returns) < self.threshold:
            return None

        target = Decimal("100") if returns > 0 else Decimal("-100")
        return Signal(
            strategy_id="trend",
            symbol=market_state.symbol,
            target_position=target,
            confidence=min(1.0, abs(returns) / self.threshold),
            timestamp=datetime.utcnow(),
            metadata={"momentum": returns, "lookback": self.lookback},
        )

