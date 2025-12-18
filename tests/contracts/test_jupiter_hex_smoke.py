import types

import pytest


def test_jupiter_hexagonal_smoke():
    # Skip cleanly if solana deps are not installed.
    pytest.importorskip("solana")

    from otq.engines.jupiter_dex_engine import JupiterDexEngine
    from otq.strategies.jupiter_mr_strategy import JupiterMRConfig

    class FakeAdapter:
        def __init__(self, prices, price_for_quote=10.0):
            self.prices = list(prices)
            self.price_for_quote = price_for_quote
            self.public_key = "fake_wallet"
            self.submit_calls = []
            self.quote_calls = []

        def get_price(self, pair: str, amount_base: float = 1.0):
            if self.prices:
                return self.prices.pop(0)
            return self.price_for_quote

        def get_quote(self, base_symbol: str, quote_symbol: str, amount_base: float):
            self.quote_calls.append((base_symbol, quote_symbol, amount_base))
            if base_symbol.upper() == "USDC":
                # Buying base token with USDC
                amount_out = amount_base / self.price_for_quote
            else:
                # Selling base token back to USDC
                amount_out = amount_base * self.price_for_quote

            return types.SimpleNamespace(
                route={"path": "fake"},
                amount_in=amount_base,
                amount_out=amount_out,
            )

        def submit_swap_order(self, route):
            self.submit_calls.append(route)
            return "sig_fake"

    cfg = JupiterMRConfig(
        pairs=["SOL/USDC"],
        rsi_period=3,
        rsi_oversold=70.0,
        take_profit_pct=0.5,
        stop_loss_pct=50.0,
        notional_per_trade=10.0,
        risk_per_trade_pct=100.0,
        max_concurrent_positions=1,
        max_hold_minutes=999,
    )

    adapter = FakeAdapter(prices=[10.0, 9.0, 8.0, 7.0, 11.0], price_for_quote=10.0)
    engine = JupiterDexEngine(config=cfg, adapter=adapter, starting_usdc=5000.0, poll_seconds=0)

    # First four loops should establish an entry after RSI becomes oversold.
    for _ in range(4):
        engine._loop_once()

    assert "SOL/USDC" in engine.strategy.positions
    assert adapter.submit_calls, "Expected entry swap submission"

    # Next loop should hit take-profit and exit.
    engine._loop_once()

    assert "SOL/USDC" not in engine.strategy.positions
    assert adapter.submit_calls, "Expected exit swap submission"
    assert engine.cash_usdc >= 4990.0  # Notional was 10 USDC

