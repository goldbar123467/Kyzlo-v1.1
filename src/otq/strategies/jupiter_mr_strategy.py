"""
Mean-reversion strategy variant for Solana spot via Jupiter.

Assumptions:
- Spot-only (no perps), long-only to keep borrow/fee model simple.
- Uses rolling RSI on recent mid-prices collected by the engine.
- Risk sizing is not leveraged; sized by notional_per_trade and risk%.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np


class DexSignal(Enum):
    LONG = 1
    FLAT = 0


@dataclass
class DexPosition:
    pair: str
    entry_price: float
    size_base: float
    notional_usdc: float
    entry_time: datetime
    take_profit: float
    stop_loss: float


@dataclass
class JupiterMRConfig:
    pairs: List[str] = field(default_factory=lambda: ["SOL/USDC"])
    
    rsi_period: int = 14
    rsi_oversold: float = 31.0        # Entry RSI threshold
    rsi_confirm_bars: int = 1         # Single tick only (no multi-bar confirmation)
    rsi_extra_margin: float = 0.0     # No extra margin required
    rsi_overbought: float = 48.0      # Early exit threshold
    take_profit_pct: float = 0.45     # TP +0.45%
    stop_loss_pct: float = 0.60       # SL -0.60%
    hard_exit_minutes: int = 25       # Hard exit at 25 minutes
    risk_per_trade_pct: float = 6.0
    notional_per_trade: float = 10.0  # $10 notional per trade
    max_concurrent_positions: int = 2
    slippage_bps: int = 75
    single_unit: bool = False

class JupiterMRStrategy:
    """Lightweight MR-like logic for DEX spot trading."""

    def __init__(self, config: Optional[JupiterMRConfig] = None):
        self.config = config or JupiterMRConfig()
        self.price_history: Dict[str, Deque[float]] = {
            p: deque(maxlen=max(200, self.config.rsi_period * 5))
            for p in self.config.pairs
        }
        self.positions: Dict[str, DexPosition] = {}

    def record_price(self, pair: str, price: float):
        if pair not in self.price_history:
            self.price_history[pair] = deque(maxlen=max(200, self.config.rsi_period * 5))
        try:
            p = float(price)
        except Exception:
            return
        if not np.isfinite(p) or p <= 0:
            return
        self.price_history[pair].append(p)

    def _calculate_rsi(self, prices: List[float]) -> float:
        if len(prices) < self.config.rsi_period + 1:
            return float("nan")

        arr = np.asarray(prices, dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size < self.config.rsi_period + 1:
            return float("nan")

        deltas = np.diff(arr[-(self.config.rsi_period + 1) :])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def generate_entry_signal(self, pair: str) -> Tuple[DexSignal, float]:
        prices = list(self.price_history.get(pair, []))
        # Need enough history to compute RSI
        required = int(self.config.rsi_period) + 1
        if len(prices) < required:
            return DexSignal.FLAT, float("nan")

        # Compute RSI for latest close
        rsi_latest = self._calculate_rsi(prices)
        if np.isnan(rsi_latest):
            return DexSignal.FLAT, rsi_latest

        # Single tick entry: RSI <= 31
        oversold_threshold = float(self.config.rsi_oversold)
        if rsi_latest <= oversold_threshold:
            return DexSignal.LONG, rsi_latest

        return DexSignal.FLAT, rsi_latest

    def size_trade(self, equity_usdc: float, price: float) -> Tuple[float, float]:
        risk_amt = equity_usdc * (self.config.risk_per_trade_pct / 100.0)
        notional = min(self.config.notional_per_trade, risk_amt)
        if price <= 0:
            return 0.0, 0.0
        # Optionally cap at a single base unit for "one lot" trades.
        if self.config.single_unit:
            notional = min(notional, price)
        size_base = notional / price
        return size_base, notional

    def open_position(self, pair: str, price: float, size_base: float) -> DexPosition:
        tp = price * (1 + self.config.take_profit_pct / 100)
        sl = price * (1 - self.config.stop_loss_pct / 100)
        pos = DexPosition(
            pair=pair,
            entry_price=price,
            size_base=size_base,
            notional_usdc=price * size_base,
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
        now = datetime.utcnow()
        elapsed = now - pos.entry_time
        elapsed_minutes = elapsed.total_seconds() / 60.0

        pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100

        # Immediate TP/SL
        if price >= pos.take_profit:
            return f"TAKE_PROFIT {pnl_pct:.2f}%"
        if price <= pos.stop_loss:
            return f"STOP_LOSS {pnl_pct:.2f}%"

        # RSI early exit: RSI >= 48
        prices = list(self.price_history.get(pair, []))
        if len(prices) >= self.config.rsi_period + 1:
            rsi_current = self._calculate_rsi(prices)
            if not np.isnan(rsi_current) and rsi_current >= float(self.config.rsi_overbought):
                return f"RSI_EXIT {pnl_pct:.2f}% (RSI={rsi_current:.1f})"

        # Hard exit at 25 minutes (unconditional)
        if elapsed_minutes >= float(self.config.hard_exit_minutes):
            return f"HARD_EXIT {pnl_pct:.2f}%"

        return None

    def can_enter(self, pair: str) -> bool:
        if pair in self.positions:
            return False
        return len(self.positions) < self.config.max_concurrent_positions


__all__ = [
    "JupiterMRStrategy",
    "JupiterMRConfig",
    "DexSignal",
    "DexPosition",
]

