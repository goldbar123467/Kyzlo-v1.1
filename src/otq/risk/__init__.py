"""Risk helpers for OTQ engines.

Perps-specific pre-trade adapters live here and wrap the existing venue-agnostic
risk rules under `domain.risk`.
"""

from .perps_pre_trade_hook import PerpsPreTradeHookConfig, make_perps_pre_trade_hook

__all__ = [
    "PerpsPreTradeHookConfig",
    "make_perps_pre_trade_hook",
]
