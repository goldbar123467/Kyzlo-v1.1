from __future__ import annotations


def test_sanitize_vs_currency_strips_inline_comments() -> None:
    from otq.engines.scanner_adapters import CoinGeckoPriceFeed

    feed = CoinGeckoPriceFeed(api_key="", vs_currency="usd # comment", cache_ttl_seconds=1)
    assert feed.vs_currency == "usd"
