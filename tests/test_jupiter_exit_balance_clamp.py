from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest


@dataclass
class _FakeToken:
    symbol: str
    mint: str
    decimals: int


class _FakeSolanaClient:
    def __init__(self, *, token_balance_raw: int = 0, sol_balance_lamports: int = 0):
        self._token_balance_raw = int(token_balance_raw)
        self._sol_balance_lamports = int(sol_balance_lamports)

    def get_public_address(self) -> str:  # pragma: no cover
        return "FakePubkey11111111111111111111111111111111111"

    def get_spl_token_balance_raw(self, mint: str) -> int:  # noqa: ARG002
        return int(self._token_balance_raw)

    def get_native_balance_lamports(self) -> int:
        return int(self._sol_balance_lamports)


def test_exit_quote_is_clamped_to_wallet_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.data.vendors.jupiter_adapter import JupiterAdapter, QuoteResult
    import otq.data.vendors.jupiter_adapter as ja

    # Stub token registry to avoid relying on full config for this unit test.
    monkeypatch.setattr(ja, "get_token", lambda s: _FakeToken(symbol=s, mint=f"mint-{s}", decimals=6))

    fake_client = _FakeSolanaClient(token_balance_raw=1_500_000)  # 1.5 tokens @ 6 decimals
    adapter = JupiterAdapter(solana_client=fake_client)

    captured: Dict[str, Any] = {}

    def _fake_get_quote(base_symbol: str, quote_symbol: str, amount_base: float, only_direct_routes: Optional[bool] = None):
        captured["base"] = base_symbol
        captured["quote"] = quote_symbol
        captured["amount_base"] = amount_base
        return QuoteResult(route={"routePlan": []}, amount_in=amount_base, amount_out=2.0 * amount_base, price_impact_pct=0.0)

    monkeypatch.setattr(adapter, "get_quote", _fake_get_quote)

    # Position wants to sell 2.0 tokens, but wallet has 1.5 minus dust.
    # dust = max(1000, int(1_500_000*0.001)=1500) => sell_raw=min(2_000_000, 1_498_500)=1_498_500 => 1.4985
    prepared = adapter.get_exit_quote_clamped("JUP", "USDC", 2.0)
    assert prepared["status"] == "ok"
    assert captured["amount_base"] == 1.4985


def test_exit_quote_returns_dust_closed_when_balance_is_too_small(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.data.vendors.jupiter_adapter import JupiterAdapter
    import otq.data.vendors.jupiter_adapter as ja

    monkeypatch.setattr(ja, "get_token", lambda s: _FakeToken(symbol=s, mint=f"mint-{s}", decimals=6))

    fake_client = _FakeSolanaClient(token_balance_raw=500)  # less than dust floor
    adapter = JupiterAdapter(solana_client=fake_client)

    # If get_quote is called here, the clamp is broken.
    monkeypatch.setattr(adapter, "get_quote", lambda *a, **k: (_ for _ in ()).throw(AssertionError("get_quote called")))

    prepared = adapter.get_exit_quote_clamped("JUP", "USDC", 1.0)
    assert prepared["status"] == "dust_closed"
