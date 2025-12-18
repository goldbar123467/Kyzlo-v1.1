import asyncio
from loguru import logger

from src.adapters.market_data.coingecko_adapter import CoinGeckoMarketDataAdapter
from src.adapters.market_data.polygon_adapter import PolygonMarketDataAdapter
from src.application.services.hybrid_market_data import HybridMarketDataService


async def main():
    # Replace with your API keys in env or direct strings.
    polygon_key = "YOUR_POLYGON_KEY"
    coingecko_key = ""  # demo key optional

    polygon = PolygonMarketDataAdapter(api_key=polygon_key)
    coingecko = CoinGeckoMarketDataAdapter(api_key=coingecko_key)
    hybrid = HybridMarketDataService(polygon, coingecko, enabled=True)

    sol_spot = await hybrid.get_tick("SOLUSD")
    logger.info(f"SOL spot (Polygon): {sol_spot.price} @ {sol_spot.timestamp}")

    sol_perp = await hybrid.get_perp_metrics("SOL")
    logger.info(f"SOL perp metrics (CG): {sol_perp}")

    enriched = await hybrid.build_enriched_tick("SOLUSD")
    logger.info(f"Enriched tick: {enriched}")

    await polygon.disconnect()
    await coingecko.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

