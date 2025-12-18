from typing import Optional
from decimal import Decimal
from datetime import datetime
import statistics

from .base import TradingStrategy
from ..events.signal import Signal


class MeanReversionModel(TradingStrategy):
    """Mean reversion strategy."""

    def __init__(self, window: int = 20, entry_z: float = 2.0, exit_z: float = 0.5):
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.price_history: list = []

    def generate_signal(
        self,
        market_state: "MarketState",
        portfolio: "Portfolio",
    ) -> Optional[Signal]:
        self.price_history.append(float(market_state.mid))
        if len(self.price_history) > self.window:
            self.price_history.pop(0)

        if len(self.price_history) < self.window:
            return None

        mean = statistics.mean(self.price_history)
        std = statistics.stdev(self.price_history)
        if std == 0:
            return None

        zscore = (self.price_history[-1] - mean) / std
        current_pos = portfolio.positions.get(market_state.symbol)
        current_qty = current_pos.quantity if current_pos else Decimal("0")

        if zscore > self.entry_z and current_qty >= 0:
            return Signal(
                strategy_id="mean_reversion",
                symbol=market_state.symbol,
                target_position=Decimal("-100"),
                confidence=min(1.0, abs(zscore) / 3),
                timestamp=datetime.utcnow(),
                metadata={"zscore": zscore},
            )
        if zscore < -self.entry_z and current_qty <= 0:
            return Signal(
                strategy_id="mean_reversion",
                symbol=market_state.symbol,
                target_position=Decimal("100"),
                confidence=min(1.0, abs(zscore) / 3),
                timestamp=datetime.utcnow(),
                metadata={"zscore": zscore},
            )
        if abs(zscore) < self.exit_z and current_qty != 0:
            return Signal(
                strategy_id="mean_reversion",
                symbol=market_state.symbol,
                target_position=Decimal("0"),
                confidence=0.8,
                timestamp=datetime.utcnow(),
                metadata={"zscore": zscore, "action": "exit"},
            )

        return None

