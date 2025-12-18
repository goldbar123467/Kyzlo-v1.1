import time
from otq.data.vendors.binance_us_adapter import BinanceUSAdapter


def on_bar(symbol, bar):
    print(f"BAR {symbol} close={bar.close} ts={bar.timestamp}")


a = BinanceUSAdapter(symbols=["ETH/USD", "DOGE/USD"], on_bar_1min=on_bar)
a.start(backfill_bars=50)

try:
    time.sleep(30)  # let it poll a few cycles
    print("latest:", a.get_latest_prices())

    # dry-run: notional order (will simulate if keys missing)
    print(a.place_market_order_notional("ETH/USD", "buy", 12))
finally:
    a.stop()
