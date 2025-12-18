from __future__ import annotations

from datetime import datetime, timedelta

from otq.strategies.jupiter_trend_pullback_scalper import JupiterTrendPullbackConfig, JupiterTrendPullbackScalper, DexSignal


def test_scalper_enters_on_uptrend_and_pullback() -> None:
    cfg = JupiterTrendPullbackConfig(
        pairs=["BONK/USDC"],
        trend_lookback=10,
        min_trend_return_pct=0.5,
        pullback_high_lookback=6,
        pullback_from_high_pct=0.8,
        pullback_rsi_period=3,
        pullback_rsi_max=60.0,
        cooldown_minutes=0,
    )
    s = JupiterTrendPullbackScalper(cfg)

    # Build an uptrend, then a pullback.
    # Strong pullback on the last point to satisfy RSI + drawdown requirements.
    prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 107.0]
    for p in prices:
        s.record_price("BONK/USDC", float(p))

    sig, meta = s.generate_entry_signal("BONK/USDC")
    assert sig == DexSignal.LONG
    assert "dd_pct" in meta


def test_scalper_time_exit() -> None:
    cfg = JupiterTrendPullbackConfig(pairs=["SOL/USDC"], max_hold_minutes=1)
    s = JupiterTrendPullbackScalper(cfg)

    pos = s.open_position("SOL/USDC", price=10.0, size_base=1.0)
    pos.entry_time = datetime.utcnow() - timedelta(minutes=2)

    reason = s.check_exit("SOL/USDC", price=10.0)
    assert reason is not None
    assert reason.startswith("TIME_EXIT")
