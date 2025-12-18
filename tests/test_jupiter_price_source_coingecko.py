from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

import pytest


class _PriceFeedStub:
    def __init__(self, prices: Dict[str, float]):
        self._prices = {k.upper(): float(v) for k, v in prices.items()}
        self.batch_calls = 0

    def get_prices_batch(self, symbols):  # noqa: ANN001
        self.batch_calls += 1
        return {s.upper(): self._prices.get(s.upper()) for s in symbols if self._prices.get(s.upper()) is not None}


class _AdapterExitOnly:
    """Adapter intentionally missing get_price to ensure it is never used."""

    public_key = "fake_wallet"

    def __init__(self, price: float = 10.0) -> None:
        self.price = float(price)
        self.submit_calls = 0

    def get_exit_quote_clamped(self, base: str, quote: str, position_amount_base: float) -> Dict[str, Any]:  # noqa: ARG002
        from otq.data.vendors.jupiter_adapter import QuoteResult

        return {
            "status": "ok",
            "quote": QuoteResult(
                route={"routePlan": []},
                amount_in=float(position_amount_base),
                amount_out=float(position_amount_base) * self.price,
                price_impact_pct=0.0,
            ),
            "position_raw": 2_000_000,
            "balance_raw": 2_000_000,
            "dust_raw": 1_000,
            "sell_raw": 1_999_000,
            "sell_amount_base": float(position_amount_base),
        }

    def submit_swap_order(self, route: Dict[str, Any]) -> str:  # noqa: ARG002
        self.submit_calls += 1
        return "sig_exit"


class _AdapterWithPriceFallback(_AdapterExitOnly):
    def __init__(self, price: float = 10.0) -> None:
        super().__init__(price=price)
        self.get_price_calls = 0

    def get_price(self, pair: str, amount_base: float = 1.0) -> float:  # noqa: ARG002
        self.get_price_calls += 1
        return float(self.price)


def test_engine_can_exit_without_jupiter_pricing(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.jupiter_dex_engine import JupiterDexEngine
    from otq.strategies.jupiter_mr_strategy import JupiterMRConfig

    monkeypatch.setenv("JUP_STRATEGY", "mr")
    monkeypatch.setenv("JUP_PRICE_SOURCE", "coingecko")

    cfg = JupiterMRConfig(
        pairs=["SOL/USDC"],
        rsi_period=3,
        max_hold_minutes=1,
        take_profit_pct=999.0,
        stop_loss_pct=999.0,
        max_concurrent_positions=1,
        notional_per_trade=10.0,
        risk_per_trade_pct=100.0,
    )

    adapter = _AdapterExitOnly(price=10.0)
    price_feed = _PriceFeedStub({"SOL": 10.0})
    engine = JupiterDexEngine(config=cfg, adapter=adapter, price_feed=price_feed, starting_usdc=0.0, poll_seconds=0)

    pos = engine.strategy.open_position("SOL/USDC", price=10.0, size_base=1.0)
    pos.entry_time = datetime.utcnow() - timedelta(minutes=2)

    engine._loop_once()

    assert price_feed.batch_calls >= 1
    assert adapter.submit_calls == 1
    assert "SOL/USDC" not in engine.strategy.positions


def test_engine_can_fallback_to_jupiter_when_coingecko_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.jupiter_dex_engine import JupiterDexEngine
    from otq.strategies.jupiter_mr_strategy import JupiterMRConfig

    monkeypatch.setenv("JUP_STRATEGY", "mr")
    monkeypatch.setenv("JUP_PRICE_SOURCE", "coingecko")
    monkeypatch.setenv("JUP_PRICE_FALLBACK", "jupiter")

    cfg = JupiterMRConfig(
        pairs=["SOL/USDC"],
        rsi_period=3,
        max_hold_minutes=999,
        take_profit_pct=999.0,
        stop_loss_pct=999.0,
        max_concurrent_positions=1,
        notional_per_trade=10.0,
        risk_per_trade_pct=100.0,
    )

    adapter = _AdapterWithPriceFallback(price=10.0)
    price_feed = _PriceFeedStub({})
    engine = JupiterDexEngine(config=cfg, adapter=adapter, price_feed=price_feed, starting_usdc=0.0, poll_seconds=0)

    engine._loop_once()

    assert price_feed.batch_calls >= 1
    assert adapter.get_price_calls == 1


def test_strict_mode_missing_coingecko_skips_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.jupiter_dex_engine import JupiterDexEngine
    from otq.strategies.jupiter_mr_strategy import JupiterMRConfig

    monkeypatch.setenv("JUP_STRATEGY", "mr")
    monkeypatch.setenv("JUP_PRICE_SOURCE", "coingecko")
    monkeypatch.setenv("JUP_PRICE_FALLBACK", "strict")

    cfg = JupiterMRConfig(
        pairs=["SOL/USDC"],
        rsi_period=3,
        max_hold_minutes=999,
        take_profit_pct=999.0,
        stop_loss_pct=999.0,
        max_concurrent_positions=1,
        notional_per_trade=10.0,
        risk_per_trade_pct=100.0,
    )

    adapter = _AdapterWithPriceFallback(price=10.0)
    price_feed = _PriceFeedStub({})
    engine = JupiterDexEngine(config=cfg, adapter=adapter, price_feed=price_feed, starting_usdc=0.0, poll_seconds=0)

    engine._loop_once()

    assert price_feed.batch_calls >= 1
    assert adapter.get_price_calls == 0
    assert "SOL/USDC" not in engine._close_window


def test_fallback_mode_caches_jupiter_price(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.jupiter_dex_engine import JupiterDexEngine
    from otq.strategies.jupiter_mr_strategy import JupiterMRConfig

    monkeypatch.setenv("JUP_STRATEGY", "mr")
    monkeypatch.setenv("JUP_PRICE_SOURCE", "coingecko")
    monkeypatch.setenv("JUP_PRICE_FALLBACK", "jupiter")
    monkeypatch.setenv("JUP_FALLBACK_PRICE_CACHE_TTL_SEC", "30")

    cfg = JupiterMRConfig(
        pairs=["SOL/USDC"],
        rsi_period=3,
        max_hold_minutes=999,
        take_profit_pct=999.0,
        stop_loss_pct=999.0,
        max_concurrent_positions=1,
        notional_per_trade=10.0,
        risk_per_trade_pct=100.0,
    )

    adapter = _AdapterWithPriceFallback(price=10.0)
    price_feed = _PriceFeedStub({})
    engine = JupiterDexEngine(config=cfg, adapter=adapter, price_feed=price_feed, starting_usdc=0.0, poll_seconds=0)

    engine._loop_once()
    engine._loop_once()

    assert adapter.get_price_calls == 1
    assert "SOL/USDC" in engine._close_window
    assert len(engine._close_window["SOL/USDC"]) >= 2
