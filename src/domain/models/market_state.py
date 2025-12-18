from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict


@dataclass
class MarketState:
    symbol: str
    timestamp: datetime
    mid: Decimal
    bid: Decimal
    ask: Decimal
    spread: Decimal
    vol_estimate: Decimal
    liquidity_score: Decimal
    features: Dict[str, float]
    regime_indicators: Dict[str, float]
    schema_version: int = 2  # versioned schema for backtest parity

    @classmethod
    def from_tick(cls, tick: "Tick") -> "MarketState":
        """Convert raw tick to normalized market state."""
        mid = (tick.bid + tick.ask) / 2 if tick.bid and tick.ask else tick.price
        spread = tick.ask - tick.bid if tick.bid and tick.ask else Decimal("0")
        return cls(
            symbol=tick.symbol,
            timestamp=tick.timestamp,
            mid=mid,
            bid=tick.bid or mid,
            ask=tick.ask or mid,
            spread=spread,
            vol_estimate=Decimal("0"),
            liquidity_score=Decimal("0"),
            features={},
            regime_indicators={},
        )

