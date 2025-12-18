from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from otq.data.vendors.jupiter_adapter import JupiterAdapter, QuoteResult


class _FakeSolanaClient:
    def get_public_address(self) -> str:  # pragma: no cover
        return "FakePubkey11111111111111111111111111111111111"


@dataclass
class _Resp:
    status_code: int
    text: str = ""
    payload: Optional[Dict[str, Any]] = None

    def json(self) -> Any:
        if self.payload is None:
            raise ValueError("no json")
        return self.payload


def test_get_price_probes_larger_amount_on_route_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = JupiterAdapter(solana_client=_FakeSolanaClient())

    # Ensure deterministic probe loop in test.
    monkeypatch.setenv("JUPITER_PRICE_PROBE_MAX_TRIES", "3")
    monkeypatch.setenv("JUPITER_PRICE_PROBE_MULTIPLIER", "10")

    def _fake_get_quote(base: str, quote: str, amount_base: float) -> Optional[QuoteResult]:
        if amount_base < 0.01:
            return None
        return QuoteResult(route={"routePlan": []}, amount_in=amount_base, amount_out=2.0 * amount_base, price_impact_pct=0.0)

    monkeypatch.setattr(adapter, "get_quote", _fake_get_quote)

    # 0.001 would fail, but probe hits 0.01 and succeeds.
    px = adapter.get_price("SOL/USDC", amount_base=0.001)
    assert px == pytest.approx(2.0)


def test_get_quote_route_not_found_is_treated_as_no_route_not_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = JupiterAdapter(solana_client=_FakeSolanaClient())

    # Avoid DNS / network.
    monkeypatch.setattr(adapter, "_resolve_host", lambda url: True)

    # Force all endpoints to respond with a 404 and Route not found message.
    def _fake_get(url: str, params: Dict[str, Any], headers: Dict[str, str], timeout: int) -> _Resp:
        return _Resp(status_code=404, text="{\"message\": \"Route not found\"}", payload={"message": "Route not found"})

    import otq.data.vendors.jupiter_adapter as ja

    monkeypatch.setattr(ja.requests, "get", _fake_get)

    q = adapter.get_quote("SOL", "USDC", 0.001)
    assert q is None
