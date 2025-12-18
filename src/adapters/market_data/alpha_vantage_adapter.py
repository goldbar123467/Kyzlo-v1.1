"""
Alpha Vantage market data adapter (REST).

Supports intraday OHLCV (1min) for U.S. equities with Basic Premium key.
This is pull-based and throttled; best for backfill or low-frequency refresh.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import List, AsyncIterator, Optional, Dict, Tuple

import httpx
from loguru import logger

from ...ports.market_data import MarketDataPort, Tick


class AlphaVantageAdapter(MarketDataPort):
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: str,
        session: Optional[httpx.AsyncClient] = None,
        cache_ttl: int = 10,
    ):
        self.api_key = api_key
        self._client = session or httpx.AsyncClient(timeout=10)
        self._cache_ttl = cache_ttl
        self._tick_cache: Dict[str, Tuple[datetime, Tick]] = {}
        self._ohlcv_cache: Dict[str, Tuple[datetime, list]] = {}

    async def subscribe(self, symbols: List[str]) -> None:
        self._subscribed = symbols

    async def stream(self) -> AsyncIterator[Tick]:
        return
        yield  # pragma: no cover

    async def get_snapshot(self, symbol: str) -> "MarketState":
        from ...domain.models.market_state import MarketState

        tick = await self.get_tick(symbol)
        return MarketState.from_tick(tick)

    async def disconnect(self) -> None:
        await self._client.aclose()

    async def get_tick(self, symbol: str) -> Tick:
        # Derive tick from the most recent bar
        bars = await self.get_ohlcv(symbol, "1min", limit=1)
        if not bars:
            raise RuntimeError(f"No intraday data for {symbol}")
        bar = bars[-1]
        price = bar["close"]
        ts = bar["ts"]
        tick = Tick(
            symbol=symbol.upper(),
            timestamp=ts,
            price=price,
            size=Decimal("0"),
            bid=None,
            ask=None,
            exchange="alphavantage",
        )
        self._tick_cache[symbol] = (datetime.utcnow(), tick)
        return tick

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        """
        Fetch intraday OHLCV using TIME_SERIES_INTRADAY with 1min interval.
        Alpha Vantage Basic Premium provides extended history; still rate-limited.
        """
        if not timeframe.endswith("m"):
            raise ValueError("Alpha Vantage intraday adapter supports minute timeframes only")

        cached = self._ohlcv_cache.get((symbol, timeframe))
        now = datetime.utcnow()
        if cached and (now - cached[0]).total_seconds() < self._cache_ttl:
            return cached[1][-limit:]

        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol.upper(),
            "interval": "1min",
            "outputsize": "full",
            "datatype": "json",
            "apikey": self.api_key,
        }
        resp = await self._request(params)
        series = resp.json().get("Time Series (1min)", {})
        bars = []
        for ts_str, row in sorted(series.items()):
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            bars.append(
                {
                    "ts": ts,
                    "open": Decimal(row["1. open"]),
                    "high": Decimal(row["2. high"]),
                    "low": Decimal(row["3. low"]),
                    "close": Decimal(row["4. close"]),
                    "volume": Decimal(row["5. volume"]),
                }
            )
        bars = bars[-limit:]
        self._ohlcv_cache[(symbol, timeframe)] = (now, bars)
        return bars

    async def get_perp_metrics(self, symbol: str):
        return None

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #
    async def _request(self, params: dict) -> httpx.Response:
        for attempt in range(3):
            resp = await self._client.get(self.BASE_URL, params=params)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 15.0
                logger.warning(f"Alpha Vantage rate limit hit; backing off {delay}s")
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            if "Note" in resp.text:
                # Alpha Vantage returns a Note on throttling
                logger.warning("Alpha Vantage throttling note received; backing off 15s")
                await asyncio.sleep(15)
                continue
            return resp
        resp.raise_for_status()
        return resp

