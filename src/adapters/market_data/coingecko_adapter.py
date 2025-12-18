import asyncio
import random
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, AsyncIterator, Optional, Dict, Tuple

import httpx
from loguru import logger

from ...ports.market_data import MarketDataPort, Tick
from ...domain.models.perp_metrics import PerpMetrics


class CoinGeckoMarketDataAdapter(MarketDataPort):
    """
    Pull-based market data adapter using CoinGecko.

    - Spot ticks via /simple/price
    - OHLCV via /coins/{id}/market_chart
    - Perp metrics via /derivatives endpoints
    """

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(
        self,
        api_key: str = "",
        quote_currency: str = "usd",
        session: Optional[httpx.AsyncClient] = None,
        cache_ttl: int = 120,
        min_interval_seconds: float = 12.0,
        backoff_base_seconds: float = 5.0,
    ):
        self.api_key = api_key
        self.quote_currency = quote_currency
        self._client = session or httpx.AsyncClient(timeout=10)
        self._cache_ttl = timedelta(seconds=cache_ttl)
        self._price_cache: Dict[str, Tuple[datetime, Tick]] = {}
        self._ohlcv_cache: Dict[str, Tuple[datetime, list]] = {}
        self._perp_cache: Dict[str, Tuple[datetime, PerpMetrics]] = {}
        self._min_interval = max(0.5, float(min_interval_seconds))
        self._backoff_base = max(1.0, float(backoff_base_seconds))
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0

        # Minimal symbol->id map; extend via config if needed.
        self.symbol_map = {
            # Majors
            "SOL": "solana",
            "SOLUSD": "solana",
            "SOLUSDT": "solana",
            "BTC": "bitcoin",
            "BTCUSD": "bitcoin",
            "BTCUSDT": "bitcoin",
            "ETH": "ethereum",
            "ETHUSD": "ethereum",
            "ETHUSDT": "ethereum",
            # Meme/alt set
            "BONK": "bonk",
            "BONKUSDT": "bonk",
            "BONKUSD": "bonk",
            "TRUMP": "official-trump",
            "TRUMPUSDT": "official-trump",
            "TRUMPUSD": "official-trump",
            "WIF": "dogwifcoin",
            "WIFUSDT": "dogwifcoin",
            "WIFUSD": "dogwifcoin",
            "PEPE": "pepe",
            "PEPEUSDT": "pepe",
            "PEPEUSD": "pepe",
            "DOGE": "dogecoin",
            "DOGEUSDT": "dogecoin",
            "DOGEUSD": "dogecoin",
        }

    async def subscribe(self, symbols: List[str]) -> None:
        # Pull-based adapter: no-op for subscribe.
        self._subscribed = symbols

    async def stream(self) -> AsyncIterator[Tick]:
        # Pull-based adapter: yields nothing; kept for interface compatibility.
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
        cached = self._price_cache.get(symbol)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        coin_id = self._resolve_id(symbol)
        params = {"ids": coin_id, "vs_currencies": self.quote_currency}
        headers = {"x-cg-demo-api-key": self.api_key} if self.api_key else None
        resp = await self._request("/simple/price", params=params, headers=headers)
        data = resp.json()
        price = Decimal(str(data[coin_id][self.quote_currency]))
        tick = Tick(
            symbol=f"{symbol.upper()}{self.quote_currency.upper()}",
            timestamp=now,
            price=price,
            size=Decimal("0"),
            bid=None,
            ask=None,
            exchange="coingecko",
        )
        self._price_cache[symbol] = (now, tick)
        return tick

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        """
        Fetch OHLC via CoinGecko's /ohlc endpoint (no volume provided; set to 0).
        Resolution is provider-defined (5m for 1 day, hourly for 7-30d, daily beyond).
        """
        now = datetime.utcnow()
        cache_key = f"{symbol}:{timeframe}:{limit}"
        cached = self._ohlcv_cache.get(cache_key)
        if cached and now - cached[0] < timedelta(minutes=5):
            return cached[1]

        coin_id = self._resolve_id(symbol)
        days = self._timeframe_to_days(timeframe, limit)
        params = {
            "vs_currency": self.quote_currency,
            "days": days,
        }
        resp = await self._request(f"/coins/{coin_id}/ohlc", params=params)
        ohlc = resp.json()  # list of [timestamp, open, high, low, close]
        bars = [
            {
                "ts": datetime.utcfromtimestamp(row[0] / 1000),
                "open": Decimal(str(row[1])),
                "high": Decimal(str(row[2])),
                "low": Decimal(str(row[3])),
                "close": Decimal(str(row[4])),
                "volume": Decimal("0"),
            }
            for row in ohlc[-limit:]
        ]
        self._ohlcv_cache[cache_key] = (now, bars)
        return bars

    async def get_perp_metrics(self, symbol: str) -> Optional[PerpMetrics]:
        now = datetime.utcnow()
        cached = self._perp_cache.get(symbol)
        if cached and now - cached[0] < timedelta(minutes=1):
            return cached[1]

        params = {}
        resp = await self._request("/derivatives", params=params)
        records = resp.json()
        sym_upper = symbol.upper()
        match = next((r for r in records if r.get("base") == sym_upper), None)
        if not match:
            return None

        metrics = PerpMetrics(
            symbol=sym_upper,
            funding_rate=Decimal(str(match.get("funding_rate", 0))),
            open_interest=Decimal(str(match.get("open_interest_usd", 0))),
            volume_24h=Decimal(str(match.get("trade_volume_24h_btc", 0))),
            timestamp=datetime.utcnow(),
        )
        self._perp_cache[symbol] = (now, metrics)
        return metrics

    # ------------------------------------------------------------------ #
    # Helpers                                                           #
    # ------------------------------------------------------------------ #
    def _resolve_id(self, symbol: str) -> str:
        key = symbol.upper()
        coin_id = self.symbol_map.get(key)
        if not coin_id:
            raise ValueError(f"Unknown CoinGecko id for symbol {symbol}")
        return coin_id

    def _timeframe_to_days(self, timeframe: str, limit: int) -> int:
        """
        Map requested timeframe/limit to CoinGecko ohlc 'days' param.
        CoinGecko supports only discrete day windows; use minimum viable window.
        """
        if timeframe.endswith("d"):
            days = max(1, int(timeframe[:-1]) * limit)
        elif timeframe.endswith("h"):
            hours = int(timeframe[:-1]) * limit
            days = max(1, (hours + 23) // 24)
        else:  # minutes or other -> approximate
            minutes = int(timeframe[:-1]) * limit if timeframe[:-1].isdigit() else limit
            days = max(1, (minutes + (60 * 24 - 1)) // (60 * 24))
        return min(days, 90)  # cap to free-tier window

    async def _request(self, path: str, params: dict, headers: Optional[dict] = None) -> httpx.Response:
        url = f"{self.BASE_URL}{path}"
        for attempt in range(2):
            # Simple global rate limit: enforce spacing between requests
            async with self._rate_lock:
                now = time.monotonic()
                delta = now - self._last_request_ts
                if delta < self._min_interval:
                    await asyncio.sleep(self._min_interval - delta)
                resp = await self._client.get(url, params=params, headers=headers)
                self._last_request_ts = time.monotonic()
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else self._backoff_base * (2 ** attempt)
                delay += random.uniform(0, 0.5)
                logger.warning(f"CoinGecko rate limit hit; backing off {delay:.1f}s")
                await asyncio.sleep(delay)
                continue
            if "api.coingecko.com/api/v3" in resp.url.host and "throttled" in resp.text.lower():
                delay = self._backoff_base * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(f"CoinGecko throttle notice; backing off {delay:.1f}s")
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

