from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class SlippageConfig:
    fixed_bps: float = 1.0
    spread_fraction: float = 0.5
    temporary_impact_eta: float = 0.1
    temporary_impact_gamma: float = 0.5
    permanent_impact_epsilon: float = 0.05
    volatility_multiplier: float = 1.0


class SlippageModel(ABC):
    @abstractmethod
    def estimate_slippage(self, order, market_state, config) -> Decimal:
        ...


class AlmgrenChrissSlippage(SlippageModel):
    """Almgren-Chriss (2000) market impact model."""

    def estimate_slippage(self, order, market_state, config: SlippageConfig) -> Decimal:
        from ..models.order import OrderType

        mid = float(market_state.mid)
        spread = float(market_state.spread)
        vol = float(market_state.vol_estimate) if market_state.vol_estimate else 0.2
        adv = float(market_state.features.get("adv", 1_000_000))
        order_size = float(order.qty)

        fixed_cost = mid * (config.fixed_bps / 10000)
        spread_cost = spread * config.spread_fraction if order.order_type == OrderType.MARKET else 0

        participation_rate = order_size / adv
        temp_impact = config.temporary_impact_eta * (participation_rate ** config.temporary_impact_gamma) * mid * vol
        perm_impact = config.permanent_impact_epsilon * participation_rate * mid

        total = fixed_cost + spread_cost + temp_impact + perm_impact
        return Decimal(str(round(total, 6)))

