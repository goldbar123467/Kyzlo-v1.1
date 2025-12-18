from __future__ import annotations

import pytest


def test_pro_key_defaults_to_pro_api_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.scanner_adapters import CoinGeckoPriceFeed

    monkeypatch.setenv("COINGECKO_PRO_API_KEY", "CG-some-pro-key")
    monkeypatch.delenv("COINGECKO_BASE_URL", raising=False)

    feed = CoinGeckoPriceFeed()
    assert "pro-api.coingecko.com" in feed.base_url
