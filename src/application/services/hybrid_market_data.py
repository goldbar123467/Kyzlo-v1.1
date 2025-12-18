from decimal import Decimal
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

from loguru import logger

from ...ports.market_data import MarketDataPort, Tick
from ...domain.models.perp_metrics import PerpMetrics


class HybridMarketDataService:
    """
    CoinGecko-only market data service for Jupiter DEX v1-lite.
    
    Single source of truth: CoinGecko for all price data.
    """

    def __init__(
        self,
        coingecko_adapter: MarketDataPort,
        enabled: bool = True,
        cache_ttl_seconds: int = 0,
    ):
        self.coingecko = coingecko_adapter
        self.enabled = enabled
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._tick_cache: Dict[str, Tuple[datetime, Tick]] = {}

    async def get_tick(self, symbol: str) -> Tick:
        now = datetime.utcnow()
        cached = self._tick_cache.get(symbol)
        if cached and self._cache_ttl.total_seconds() > 0:
            ts, tick = cached
            if now - ts < self._cache_ttl:
                return tick

        tick = await self.coingecko.get_tick(symbol)
        self._tick_cache[symbol] = (now, tick)
        return tick

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        return await self.coingecko.get_ohlcv(symbol, timeframe, limit)

    async def get_perp_metrics(self, symbol: str) -> Optional[PerpMetrics]:
        try:
            return await self.coingecko.get_perp_metrics(symbol)
        except Exception as exc:
            logger.warning(f"Perp metrics fetch failed ({symbol}): {exc}")
            return None

    async def get_perp_proxy_price(self, symbol: str) -> Optional[Decimal]:
        """
        Synthetic perp proxy: spot price adjusted by funding basis.
        basis ≈ funding_rate * 24 hours * spot
        """
        tick = await self.get_tick(symbol)
        perp = await self.get_perp_metrics(symbol)
        if not perp:
            return None
        basis = perp.funding_rate * Decimal("24")
        return tick.price + (tick.price * basis)

    async def build_enriched_tick(self, symbol: str) -> Dict:
        tick = await self.get_tick(symbol)
        perp = await self.get_perp_metrics(symbol)
        proxy = await self.get_perp_proxy_price(symbol)
        return {
            "symbol": symbol,
            "spot_price": tick.price,
            "timestamp": tick.timestamp,
            "perp_funding": perp.funding_rate if perp else None,
            "open_interest": perp.open_interest if perp else None,
            "volume_24h": perp.volume_24h if perp else None,
            "perp_proxy_price": proxy,
        }

