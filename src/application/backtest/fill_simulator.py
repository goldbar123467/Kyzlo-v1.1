from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Optional
import numpy as np


@dataclass
class SimulatedFill:
    order_id: str
    fill_price: Decimal
    fill_qty: Decimal
    slippage: Decimal
    fill_time_offset: timedelta
    partial_fill: bool = False


class BacktestFillSimulator:
    """Simulates fills with configurable slippage realism."""

    def __init__(self, slippage_model, limit_fill_model=None, realism_level="REALISTIC", seed=42):
        self.slippage_model = slippage_model
        self.limit_fill_model = limit_fill_model
        self.realism_level = realism_level.upper()
        self.rng = np.random.default_rng(seed)

    def simulate_fill(self, order, market_state, slippage_config) -> Optional[SimulatedFill]:
        from ...domain.models.order import OrderType, Side

        if self.realism_level == "INSTANT":
            return SimulatedFill(
                order_id=order.id,
                fill_price=market_state.mid,
                fill_qty=order.qty,
                slippage=Decimal("0"),
                fill_time_offset=timedelta(0),
            )

        if order.order_type == OrderType.MARKET:
            slippage = self.slippage_model.estimate_slippage(order, market_state, slippage_config)
            if self.realism_level == "ADVERSE":
                # Stress: worst side of book plus extra impact
                slippage *= Decimal("1.5")
            fill_price = (
                market_state.ask + slippage if order.side == Side.BUY else market_state.bid - slippage
            )
            return SimulatedFill(
                order_id=order.id,
                fill_price=fill_price,
                fill_qty=order.qty,
                slippage=slippage,
                fill_time_offset=timedelta(seconds=self.rng.exponential(0.1)),
            )

        if self.limit_fill_model:
            fill_time = self.limit_fill_model.simulate_fill_time(order, market_state, 300, self.rng)
            if fill_time is None:
                return None
            return SimulatedFill(
                order_id=order.id,
                fill_price=order.limit_price,
                fill_qty=order.qty,
                slippage=Decimal("0"),
                fill_time_offset=timedelta(seconds=fill_time),
            )

        return None

