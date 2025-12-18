from abc import ABC, abstractmethod
from typing import List, AsyncIterator, Optional
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Tick:
    """Raw market data tick."""

    symbol: str
    timestamp: datetime
    price: Decimal
    size: Decimal
    bid: Decimal = None
    ask: Decimal = None
    exchange: str = None


class MarketDataPort(ABC):
    """Market data feed abstraction."""

    @abstractmethod
    async def subscribe(self, symbols: List[str]) -> None:
        ...

    @abstractmethod
    async def stream(self) -> AsyncIterator[Tick]:
        ...

    @abstractmethod
    async def get_snapshot(self, symbol: str) -> "MarketState":
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    # ------------------------------------------------------------------
    # Optional convenience methods for pull-based workflows.
    # Implementers may override; defaults raise NotImplementedError.
    # ------------------------------------------------------------------
    async def get_tick(self, symbol: str) -> Tick:
        """Fetch a single latest tick (spot)."""
        raise NotImplementedError

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        """Fetch OHLCV bars; timeframe examples: '1m', '5m', '1h', '1d'."""
        raise NotImplementedError

    async def get_perp_metrics(self, symbol: str) -> Optional["PerpMetrics"]:
        """Fetch perp funding/open-interest/volume if available."""
        raise NotImplementedError

