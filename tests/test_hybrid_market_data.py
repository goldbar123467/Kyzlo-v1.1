import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.application.services.hybrid_market_data import HybridMarketDataService
from src.ports.market_data import MarketDataPort, Tick


class FakeAdapter(MarketDataPort):
    def __init__(self, tick: Tick, fail: bool = False):
        self.tick = tick
        self.fail = fail
        self.calls = 0

    async def subscribe(self, symbols):
        return None

    async def stream(self):
        return
        yield  # pragma: no cover

    async def get_snapshot(self, symbol: str):
        return None

    async def disconnect(self):
        return None

    async def get_tick(self, symbol: str) -> Tick:
        self.calls += 1
        if self.fail:
            raise RuntimeError("fail")
        return self.tick

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        return []

    async def get_perp_metrics(self, symbol: str):
        return None


def make_tick(price: str = "10", symbol: str = "SOLUSD"):
    return Tick(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        price=Decimal(price),
        size=Decimal("1"),
    )


@pytest.mark.anyio
async def test_primary_success():
    primary = FakeAdapter(make_tick("11"))
    fallback = FakeAdapter(make_tick("9"))
    svc = HybridMarketDataService(primary, fallback, enabled=True)
    tick = await svc.get_tick("SOLUSD")
    assert tick.price == Decimal("11")
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.anyio
async def test_fallback_on_error():
    primary = FakeAdapter(make_tick("11"), fail=True)
    fallback = FakeAdapter(make_tick("9"))
    svc = HybridMarketDataService(primary, fallback, enabled=True)
    tick = await svc.get_tick("SOLUSD")
    assert tick.price == Decimal("9")
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.anyio
async def test_tick_cache_respects_ttl():
    primary = FakeAdapter(make_tick("11"))
    fallback = FakeAdapter(make_tick("9"))
    svc = HybridMarketDataService(primary, fallback, enabled=True, cache_ttl_seconds=5)
    first = await svc.get_tick("SOLUSD")
    second = await svc.get_tick("SOLUSD")
    assert first.price == second.price == Decimal("11")
    assert primary.calls == 1  # cached second call
    assert fallback.calls == 0

