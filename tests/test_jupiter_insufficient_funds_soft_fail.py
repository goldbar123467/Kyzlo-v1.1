from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict

import pytest


@dataclass
class _Pos:
    size_base: float


class _FakeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def get_exit_quote_clamped(self, base: str, quote: str, position_amount_base: float) -> Dict[str, Any]:  # noqa: ARG002
        self.calls += 1
        # Always say we can sell exactly the position amount.
        from otq.data.vendors.jupiter_adapter import QuoteResult

        return {
            "status": "ok",
            "quote": QuoteResult(route={"routePlan": []}, amount_in=position_amount_base, amount_out=1.0, price_impact_pct=0.0),
            "position_raw": 2_000_000,
            "balance_raw": 2_000_000,
            "dust_raw": 1_000,
            "sell_raw": 1_999_000,
            "sell_amount_base": 1.999,
        }

    def submit_swap_order(self, route: Dict[str, Any]) -> str:  # noqa: ARG002
        raise RuntimeError("InsufficientFunds custom program error: 0x1788 (6024)")


def test_exit_insufficient_funds_is_soft_failure_sets_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.jupiter_dex_engine import JupiterDexEngine

    adapter = _FakeAdapter()

    # Provide starting_usdc to avoid wallet RPC calls.
    engine = JupiterDexEngine(adapter=adapter, starting_usdc=0.0, poll_seconds=1)

    # Replace strategy with minimal stub.
    positions = {"JUP/USDC": _Pos(size_base=2.0)}

    def _close_position(pair: str):
        return positions.pop(pair, None)

    engine.strategy = SimpleNamespace(positions=positions, close_position=_close_position)
    engine.enable_portfolio_manager = False

    engine._exit_position("JUP/USDC")

    # Position should remain (soft failure).
    assert "JUP/USDC" in positions

    # Backoff should be set.
    assert engine._exit_next_allowed_ts.get("JUP/USDC", 0) > 0


def test_exit_insufficient_funds_can_dust_close(monkeypatch: pytest.MonkeyPatch) -> None:
    from otq.engines.jupiter_dex_engine import JupiterDexEngine

    class _AdapterDustOnRefresh(_FakeAdapter):
        def get_exit_quote_clamped(self, base: str, quote: str, position_amount_base: float) -> Dict[str, Any]:  # noqa: ARG002
            self.calls += 1
            if self.calls >= 2:
                return {
                    "status": "dust_closed",
                    "reason": "dust_or_insufficient_balance",
                    "position_raw": 2_000_000,
                    "balance_raw": 500,
                    "dust_raw": 1_000,
                    "sell_raw": 0,
                    "sell_amount_base": 0.0,
                }
            return super().get_exit_quote_clamped(base, quote, position_amount_base)

    adapter = _AdapterDustOnRefresh()
    engine = JupiterDexEngine(adapter=adapter, starting_usdc=0.0, poll_seconds=1)

    positions = {"JUP/USDC": _Pos(size_base=2.0)}

    def _close_position(pair: str):
        return positions.pop(pair, None)

    engine.strategy = SimpleNamespace(positions=positions, close_position=_close_position)
    engine.enable_portfolio_manager = False

    engine._exit_position("JUP/USDC")

    # Dust-close should remove the position.
    assert "JUP/USDC" not in positions
