import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, AsyncIterator

from ...ports.market_data import MarketDataPort, Tick


class MockMarketDataAdapter(MarketDataPort):
    """Simple in-memory tick generator for testing."""

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self._running = False
        self._ticks: List[Tick] = []
        now = datetime.utcnow()
        for i in range(5):
            for sym in symbols:
                px = Decimal("500") + Decimal(i) * Decimal("0.5")
                self._ticks.append(
                    Tick(
                        symbol=sym,
                        timestamp=now + timedelta(seconds=i),
                        price=px,
                        size=Decimal("1"),
                        bid=px - Decimal("0.05"),
                        ask=px + Decimal("0.05"),
                        exchange="MOCK",
                    )
                )

    async def subscribe(self, symbols: List[str]) -> None:
        self.symbols = symbols
        self._running = True

    async def stream(self) -> AsyncIterator[Tick]:
        for tick in self._ticks:
            yield tick
            await asyncio.sleep(0.01)

    async def get_snapshot(self, symbol: str) -> "MarketState":
        from ...domain.models.market_state import MarketState

        snap = next((t for t in reversed(self._ticks) if t.symbol == symbol), None)
        if not snap:
            raise ValueError(f"No tick for {symbol}")
        return MarketState.from_tick(snap)

    async def disconnect(self) -> None:
        self._running = False

