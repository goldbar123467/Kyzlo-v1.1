from abc import ABC, abstractmethod
from typing import Optional


class TradingStrategy(ABC):
    """Pure strategy interface - no I/O."""

    @abstractmethod
    def generate_signal(
        self,
        market_state: "MarketState",
        portfolio: "Portfolio",
    ) -> Optional["Signal"]:
        ...

