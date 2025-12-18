from typing import Optional
from decimal import Decimal
from datetime import datetime

from .base import TradingStrategy
from ..events.signal import Signal


class MicrostructureModel(TradingStrategy):
    """Order-flow and microstructure signal model."""

    def __init__(self, spread_threshold: float = 0.002, imbalance_threshold: float = 0.3):
        self.spread_threshold = spread_threshold
        self.imbalance_threshold = imbalance_threshold

    def generate_signal(
        self,
        market_state: "MarketState",
        portfolio: "Portfolio",
    ) -> Optional[Signal]:
        spread_pct = float(market_state.spread / market_state.mid)
        if spread_pct < self.spread_threshold:
            return None

        imbalance = market_state.features.get("volume_imbalance", 0)
        if abs(imbalance) < self.imbalance_threshold:
            return None

        target = Decimal("50") if imbalance > 0 else Decimal("-50")
        return Signal(
            strategy_id="microstructure",
            symbol=market_state.symbol,
            target_position=target,
            confidence=min(1.0, abs(imbalance)),
            timestamp=datetime.utcnow(),
            metadata={"spread_pct": spread_pct, "imbalance": imbalance},
        )

