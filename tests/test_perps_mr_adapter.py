from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from otq.coordinator import Coordinator, CoordinatorConfig
from otq.engines.perps_execution_engine import PerpsSignal
from otq.strategies.jupiter_mr_strategy import JupiterMRConfig
from otq.strategies.perps_mr_adapter import PerpsMRSignalAdapter


def _feed_decreasing_prices(adapter: PerpsMRSignalAdapter, symbol: str, *, start: float = 100.0, steps: int = 16) -> float:
    price = float(start)
    for _ in range(steps):
        adapter.record_price(symbol, price)
        price -= 1.0
    return price + 1.0


def test_adapter_returns_long_when_oversold_and_can_enter_true():
    cfg = JupiterMRConfig(pairs=["SOL/USDC"], rsi_period=14, rsi_oversold=40.0, max_concurrent_positions=1)
    adapter = PerpsMRSignalAdapter.from_config(cfg)

    last_price = _feed_decreasing_prices(adapter, "SOL/USDC", steps=cfg.rsi_period + 2)
    sig = adapter.get_signal("SOL/USDC", last_price)

    assert isinstance(sig, PerpsSignal)
    assert sig.symbol == "SOL/USDC"
    assert sig.desired == "LONG"


@pytest.mark.parametrize(
    "exit_kind",
    ["tp", "sl", "time"],
)
def test_adapter_returns_flat_when_in_position_and_exit_triggers(exit_kind: str):
    cfg = JupiterMRConfig(
        pairs=["SOL/USDC"],
        rsi_period=14,
        max_concurrent_positions=1,
        take_profit_pct=1.0,
        stop_loss_pct=1.0,
        max_hold_minutes=1,
    )
    adapter = PerpsMRSignalAdapter.from_config(cfg)

    # Open a synthetic MR position directly (perps sizing is owned elsewhere).
    pos = adapter.mr.open_position("SOL/USDC", 100.0, size_base=1.0)

    if exit_kind == "tp":
        px = pos.take_profit + 0.01
    elif exit_kind == "sl":
        px = pos.stop_loss - 0.01
    else:
        # Force time exit deterministically by backdating entry_time.
        pos.entry_time = datetime.utcnow() - timedelta(minutes=cfg.max_hold_minutes + 5)
        px = 100.0

    sig = adapter.get_signal("SOL/USDC", float(px))
    assert sig.desired == "FLAT"


def test_adapter_returns_flat_when_not_enough_price_history():
    cfg = JupiterMRConfig(pairs=["SOL/USDC"], rsi_period=14, max_concurrent_positions=1)
    adapter = PerpsMRSignalAdapter.from_config(cfg)

    # Fewer than rsi_period+1 datapoints.
    for p in [100.0, 99.0, 98.5, 98.0]:
        adapter.record_price("SOL/USDC", p)

    sig = adapter.get_signal("SOL/USDC", 98.0)
    assert sig.desired == "FLAT"


def test_adapter_returns_flat_when_max_concurrent_positions_reached():
    cfg = JupiterMRConfig(pairs=["SOL/USDC", "JUP/USDC"], rsi_period=14, max_concurrent_positions=1)
    adapter = PerpsMRSignalAdapter.from_config(cfg)

    # Fill the single allowed slot with a different pair.
    adapter.mr.open_position("SOL/USDC", 100.0, size_base=1.0)

    # Even if JUP is oversold, can_enter must block due to max positions reached.
    _feed_decreasing_prices(adapter, "JUP/USDC", steps=cfg.rsi_period + 2)
    sig = adapter.get_signal("JUP/USDC", 80.0)
    assert sig.desired == "FLAT"


def test_coordinator_wires_mr_signal_source_when_env_enabled(monkeypatch: pytest.MonkeyPatch):
    # Avoid network calls by stubbing Helius price batch.
    from otq.engines import scanner_adapters

    monkeypatch.setattr(
        scanner_adapters.HeliusPriceFeed,
        "get_prices_batch",
        lambda self, symbols: {s: 100.0 for s in symbols},
        raising=True,
    )

    monkeypatch.setenv("PERPS_SIGNAL_SOURCE", "mr")

    cfg = CoordinatorConfig(enable_binanceus=False, enable_jupiter=False, enable_perps=True, paper=True)
    coord = Coordinator(cfg)

    assert coord.perps_signal_provider is not None
    assert coord.perps_price_provider is not None

    # One tick worth of outputs should be well-typed and non-crashing.
    signals = coord.perps_signal_provider()
    prices = coord.perps_price_provider()

    assert isinstance(signals, list)
    assert isinstance(prices, dict)
    assert all(isinstance(s, PerpsSignal) for s in signals)
    assert all(isinstance(v, float) for v in prices.values())
