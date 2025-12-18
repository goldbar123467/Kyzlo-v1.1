from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Any, Optional


@dataclass
class RiskConfig:
    max_position_size: Decimal
    max_leverage: Decimal
    max_daily_loss: Decimal
    max_notional_per_order: Decimal
    fat_finger_multiplier: float = 10.0


@dataclass
class RunConfig:
    """Complete run configuration - versionable."""

    run_id: str
    git_hash: str
    config_version: int

    enabled_strategies: List[str]
    strategy_params: Dict[str, Dict[str, Any]]

    risk_limits: RiskConfig

    enabled_venues: List[str]
    venue_routing: Dict[str, str]

    regime_model_config: Dict[str, Any]
    ensemble_weights: Dict[str, List[float]]

    instruments: List[str]
    latency_tier: int
    seed: Optional[int] = None
    initial_capital: Decimal = Decimal("100000")

