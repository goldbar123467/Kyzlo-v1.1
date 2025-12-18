from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

import pytest


class _FakeExchange:
    def __init__(self) -> None:
        self.markets: Dict[str, Dict[str, Any]] = {
            "BTC/USD": {
                "limits": {"amount": {"min": 0}, "cost": {"min": 0}},
                "precision": {"amount": 8},
            }
        }

    def load_markets(self) -> None:
        return None

    def market(self, symbol: str) -> Dict[str, Any]:
        return self.markets[symbol]

    def amount_to_precision(self, symbol: str, amount: float) -> str:  # noqa: ARG002
        return str(float(amount))

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:  # noqa: ARG002
        return {"last": 100.0}


def _load_binance_us_adapter_module(monkeypatch: pytest.MonkeyPatch):
    # Avoid importing otq.data (it imports other vendors which may require optional deps).
    # Also stub pandas/numpy so this unit test can run in minimal envs.
    fake_pd = ModuleType("pandas")
    fake_np = ModuleType("numpy")
    # pytest.approx checks numpy.isscalar if numpy is importable.
    setattr(fake_np, "isscalar", lambda obj: False)
    # pytest.approx also checks numpy.bool_ when numpy is importable.
    setattr(fake_np, "bool_", bool)
    setattr(fake_np, "ndarray", type("ndarray", (), {}))
    monkeypatch.setitem(sys.modules, "pandas", fake_pd)
    monkeypatch.setitem(sys.modules, "numpy", fake_np)

    adapter_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "otq"
        / "data"
        / "vendors"
        / "binance_us_adapter.py"
    )
    spec = importlib.util.spec_from_file_location("_binance_us_adapter_test", adapter_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_paper_close_sells_simulated_holding(monkeypatch: pytest.MonkeyPatch) -> None:
    bua = _load_binance_us_adapter_module(monkeypatch)

    # Inject fake ccxt module + exchange factory.
    bua.CCXT_AVAILABLE = True

    class _FakeCcxt:
        def binanceus(self, config: Dict[str, Any]) -> _FakeExchange:  # noqa: ARG002
            return _FakeExchange()

    monkeypatch.setattr(bua, "ccxt", _FakeCcxt(), raising=False)

    adapter = bua.BinanceUSAdapter(symbols=["BTC/USD"], paper=True)

    # Seed a price so notional sizing works without network.
    adapter.latest_prices["BTC/USD"] = 100.0

    buy = adapter.place_market_order("BTC/USD", "buy", 0.5)
    assert "error" not in buy

    closed = adapter.close_position("BTC/USD")
    assert "error" not in closed
    assert closed["status"] == "simulated"
    assert closed["symbol"] == "BTC/USD"
    assert closed["side"] == "sell"
    assert closed["amount"] == 0.5

    # Second close should be a no-op success (no error), since holding is gone.
    closed2 = adapter.close_position("BTC/USD")
    assert "error" not in closed2
    assert closed2["status"] == "simulated"


def test_tiny_paper_notional_bypass_updates_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    bua = _load_binance_us_adapter_module(monkeypatch)

    bua.CCXT_AVAILABLE = True

    class _FakeCcxt:
        def binanceus(self, config: Dict[str, Any]) -> _FakeExchange:  # noqa: ARG002
            return _FakeExchange()

    monkeypatch.setattr(bua, "ccxt", _FakeCcxt(), raising=False)
    monkeypatch.setenv("BINANCE_ALLOW_TINY_PAPER_ORDERS", "1")

    adapter = bua.BinanceUSAdapter(symbols=["BTC/USD"], paper=True)
    adapter.latest_prices["BTC/USD"] = 100.0

    buy = adapter.place_market_order_notional("BTC/USD", "buy", 3.0)
    assert "error" not in buy
    assert buy["status"] == "simulated"

    positions = adapter.get_positions()
    assert "BTC" in positions
    assert positions["BTC"] == pytest.approx(0.03)
    assert "_by_symbol" in positions
    assert positions["_by_symbol"]["BTC/USD"] == pytest.approx(0.03)

    closed = adapter.close_position("BTC/USD")
    assert "error" not in closed
    assert closed["status"] == "simulated"
    assert closed["amount"] == pytest.approx(0.03)


def test_live_still_enforces_internal_min_notional(monkeypatch: pytest.MonkeyPatch) -> None:
    bua = _load_binance_us_adapter_module(monkeypatch)

    bua.CCXT_AVAILABLE = True

    class _FakeCcxt:
        def binanceus(self, config: Dict[str, Any]) -> _FakeExchange:  # noqa: ARG002
            return _FakeExchange()

    monkeypatch.setattr(bua, "ccxt", _FakeCcxt(), raising=False)
    monkeypatch.setenv("BINANCE_ALLOW_TINY_PAPER_ORDERS", "1")

    # Live mode: even if bypass flag is set, internal min notional must still apply.
    adapter = bua.BinanceUSAdapter(symbols=["BTC/USD"], paper=False)
    blocked = adapter.place_market_order_notional("BTC/USD", "buy", 3.0)
    assert blocked.get("error") == "internal_min_notional"
