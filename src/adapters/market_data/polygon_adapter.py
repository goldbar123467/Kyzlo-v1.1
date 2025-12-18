import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, AsyncIterator, Optional, Dict, Tuple

import httpx
from loguru import logger

from ...ports.market_data import MarketDataPort, Tick


class PolygonMarketDataAdapter(MarketDataPort):
    """
    Polygon.io crypto market data adapter (spot-focused).

    Uses pull-based REST to remain US-friendly and avoid venue geoblocking.
    """

    BASE_URL = "https://api.polygon.io"

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        session: Optional[httpx.AsyncClient] = None,
        cache_ttl: int = 2,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self._client = session or httpx.AsyncClient(timeout=10)
        self._cache_ttl = timedelta(seconds=cache_ttl)
        self._tick_cache: Dict[str, Tuple[datetime, Tick]] = {}
        self._ohlcv_cache: Dict[str, Tuple[datetime, list]] = {}

    async def subscribe(self, symbols: List[str]) -> None:
        self._subscribed = symbols

    async def stream(self) -> AsyncIterator[Tick]:
        # REST-only adapter; no streaming support.
        return
        yield  # pragma: no cover

    async def get_snapshot(self, symbol: str) -> "MarketState":
        from ...domain.models.market_state import MarketState

        tick = await self.get_tick(symbol)
        return MarketState.from_tick(tick)

    async def disconnect(self) -> None:
        await self._client.aclose()

    async def get_tick(self, symbol: str) -> Tick:
        now = datetime.utcnow()
        cached = self._tick_cache.get(symbol)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        ticker = self._format_ticker(symbol)
        url = f"{self.base_url}/v2/last/trade/crypto/{ticker}"
        params = {"apiKey": self.api_key}
        resp = await self._request(url, params)
        result = resp.json().get("results", {})
        price = Decimal(str(result.get("p")))
        ts = datetime.utcfromtimestamp(result.get("t") / 1_000_000_000)
        tick = Tick(
            symbol=symbol,
            timestamp=ts,
            price=price,
            size=Decimal(str(result.get("s", 0))),
            bid=None,
            ask=None,
            exchange=result.get("x"),
        )
        self._tick_cache[symbol] = (now, tick)
        return tick

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        now = datetime.utcnow()
        cache_key = f"{symbol}:{timeframe}:{limit}"
        cached = self._ohlcv_cache.get(cache_key)
        if cached and now - cached[0] < timedelta(minutes=2):
            return cached[1]

        mult, unit = self._parse_timeframe(timeframe)
        ticker = self._format_ticker(symbol)
        end = datetime.utcnow()
        start = end - self._timeframe_delta(timeframe, limit)
        url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/{mult}/{unit}/{int(start.timestamp()*1000)}/{int(end.timestamp()*1000)}"
        params = {"apiKey": self.api_key, "limit": limit}
        resp = await self._request(url, params)
        results = resp.json().get("results", [])[-limit:]
        bars = [
            {
                "ts": datetime.utcfromtimestamp(r["t"] / 1000),
                "open": Decimal(str(r["o"])),
                "high": Decimal(str(r["h"])),
                "low": Decimal(str(r["l"])),
                "close": Decimal(str(r["c"])),
                "volume": Decimal(str(r.get("v", 0))),
            }
            for r in results
        ]
        self._ohlcv_cache[cache_key] = (now, bars)
        return bars

    async def get_perp_metrics(self, symbol: str):
        # Polygon spot adapter does not provide perp metrics.
        return None

    # ------------------------------------------------------------------ #
    # Helpers                                                           #
    # ------------------------------------------------------------------ #
    def _format_ticker(self, symbol: str) -> str:
        # Expect symbols like "SOLUSD" or "BTCUSD"; polygon crypto uses "X:SOLUSD".
        cleaned = symbol.replace("/", "").upper()
        if not cleaned.startswith("X:"):
            cleaned = f"X:{cleaned}"
        return cleaned

    def _parse_timeframe(self, timeframe: str) -> Tuple[int, str]:
        unit = timeframe[-1]
        mult = int(timeframe[:-1])
        if unit == "m":
            return mult, "minute"
        if unit == "h":
            return mult, "hour"
        if unit == "d":
            return mult, "day"
        raise ValueError(f"Unsupported timeframe {timeframe}")

    def _timeframe_delta(self, timeframe: str, limit: int) -> timedelta:
        mult, unit = self._parse_timeframe(timeframe)
        if unit == "minute":
            return timedelta(minutes=mult * limit)
        if unit == "hour":
            return timedelta(hours=mult * limit)
        if unit == "day":
            return timedelta(days=mult * limit)
        return timedelta(days=limit)

    async def _request(self, url: str, params: dict) -> httpx.Response:
        for attempt in range(2):
            resp = await self._client.get(url, params=params)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 1.0
                logger.warning(f"Polygon rate limit hit; backing off {delay}s")
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

