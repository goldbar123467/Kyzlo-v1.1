"""RSI bands strategy (Conservative Scalper) for Jupiter spot.

Entry: long when RSI <= 31 (single tick).
Exit: 
  - Phase 1 (0-5 min): TP at +0.35%
  - Phase 2 (5-15 min): hold, only hard stop active
  - Hard stop: -0.85% (always active)
  - RSI exit: RSI >= 52
  - Forced exit: 15 minutes

This strategy is intentionally minimal and follows the same strategy API used by the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple
from collections import deque

import numpy as np



from otq.strategies.jupiter_mr_strategy import DexSignal

@dataclass
class DexPosition:
    pair: str
    entry_price: float
    size_base: float
    notional_usdc: float
    entry_time: datetime
    take_profit: float = 0.0  # For phase 1 TP tracking
    stop_loss: float = 0.0    # For hard stop tracking


@dataclass
class JupiterRSIBandsConfig:
    pairs: List[str] = field(default_factory=lambda: ["JUP/USDC", "SOL/USDC"]) 

    # RSI window
    lookback_points: int = 45
    rsi_period: int = 14
    rsi_oversold: float = 31.0        # Entry RSI threshold
    rsi_overbought: float = 52.0      # RSI exit threshold

    # Execution / sizing
    risk_per_trade_pct: float = 0.75
    notional_per_trade: float = 10.0  # $10 notional per trade
    max_concurrent_positions: int = 3
    slippage_bps: int = 150
    single_unit: bool = False

    # Exits
    phase1_tp_pct: float = 0.35       # Phase 1 TP +0.35% (0-5 minutes)
    phase1_duration_min: int = 5      # Phase 1 duration: 0-5 minutes
    forced_exit_min: int = 15         # Forced exit at 15 minutes
    stop_loss_pct: float = 0.85       # Hard stop -0.85%


class JupiterRSIBandsStrategy:
    """Simple RSI bands strategy implementing the engine strategy API."""

    def __init__(self, config: Optional[JupiterRSIBandsConfig] = None):
        self.config = config or JupiterRSIBandsConfig()
        self.price_history: Dict[str, Deque[float]] = {p: deque(maxlen=max(500, self.config.lookback_points * 5)) for p in self.config.pairs}
        self.positions: Dict[str, DexPosition] = {}

    def record_price(self, pair: str, price: float) -> None:
        if pair not in self.price_history:
            self.price_history[pair] = deque(maxlen=max(500, self.config.lookback_points * 5))
        try:
            p = float(price)
        except Exception:
            return
        if not np.isfinite(p) or p <= 0:
            return
        self.price_history[pair].append(p)

    def _rsi(self, prices: List[float], period: int) -> float:
        if len(prices) < period + 1:
            return float("nan")
        arr = np.asarray(prices[-(period + 1) :], dtype=float)
        deltas = np.diff(arr)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def generate_entry_signal(self, pair: str) -> Tuple[DexSignal, float]:
        """Generate entry signal. Returns (signal, rsi_value) for engine compatibility."""
        prices = list(self.price_history.get(pair, []))
        if len(prices) < max(self.config.lookback_points, self.config.rsi_period) + 1:
            return DexSignal.FLAT, float("nan")

        # Compute RSI on the lookback window
        window = prices[-self.config.lookback_points :]
        rsi = self._rsi(window, int(self.config.rsi_period))
        if not np.isfinite(rsi):
            return DexSignal.FLAT, float("nan")

        if rsi <= float(self.config.rsi_oversold):
            return DexSignal.LONG, float(rsi)
        return DexSignal.FLAT, float(rsi)

    def size_trade(self, equity_usdc: float, price: float) -> Tuple[float, float]:
        risk_amt = float(equity_usdc) * (float(self.config.risk_per_trade_pct) / 100.0)
        notional = min(float(self.config.notional_per_trade), float(risk_amt))
        if price <= 0:
            return 0.0, 0.0
        if self.config.single_unit:
            notional = min(notional, float(price))
        size_base = float(notional) / float(price)
        return float(size_base), float(notional)

    def open_position(self, pair: str, price: float, size_base: float) -> DexPosition:
        tp = price * (1 + self.config.phase1_tp_pct / 100)
        sl = price * (1 - self.config.stop_loss_pct / 100)
        pos = DexPosition(
            pair=pair,
            entry_price=float(price),
            size_base=float(size_base),
            notional_usdc=float(price) * float(size_base),
            entry_time=datetime.utcnow(),
            take_profit=tp,
            stop_loss=sl,
        )
        self.positions[pair] = pos
        return pos

    def close_position(self, pair: str) -> Optional[DexPosition]:
        return self.positions.pop(pair, None)

    def check_exit(self, pair: str, price: float) -> Optional[str]:
        pos = self.positions.get(pair)
        if not pos:
            return None
        px = float(price)
        now = datetime.utcnow()
        elapsed = now - pos.entry_time
        elapsed_minutes = elapsed.total_seconds() / 60.0

        pnl_pct = ((px - pos.entry_price) / pos.entry_price) * 100.0

        # Hard stop: -0.85% (always active)
        if px <= pos.stop_loss:
            return f"STOP_LOSS {pnl_pct:.4f}%"

        # Phase 1 (0-5 minutes): TP at +0.35%
        if elapsed_minutes <= float(self.config.phase1_duration_min):
            if px >= pos.take_profit:
                return f"TAKE_PROFIT_PHASE1 {pnl_pct:.2f}%"

        # Phase 2 (5-15 minutes): hold, only hard stop active
        # RSI exit: RSI >= 52
        prices = list(self.price_history.get(pair, []))
        if len(prices) >= max(self.config.lookback_points, self.config.rsi_period) + 1:
            window = prices[-self.config.lookback_points :]
            rsi = self._rsi(window, int(self.config.rsi_period))
            if np.isfinite(rsi) and rsi >= float(self.config.rsi_overbought):
                return f"RSI_EXIT {pnl_pct:.2f}% (RSI={rsi:.1f})"

        # Forced exit at 15 minutes
        if elapsed_minutes >= float(self.config.forced_exit_min):
            return f"FORCED_EXIT {pnl_pct:.2f}%"

        return None

    def can_enter(self, pair: str) -> bool:
        if pair in self.positions:
            return False
        return len(self.positions) < int(self.config.max_concurrent_positions)


__all__ = [
    "JupiterRSIBandsStrategy",
    "JupiterRSIBandsConfig",
]
