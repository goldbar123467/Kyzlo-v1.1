from decimal import Decimal
from typing import Dict

from ..models.regime import Regime


class WalletAllocationRules:
    """Multi-wallet capital management."""

    def allocate_capital(
        self,
        regime: Regime,
        total_capital: Decimal,
        accounts: Dict[str, "LogicalAccount"],
    ) -> Dict[str, Decimal]:
        allocations = {
            Regime.TREND: {"live": 0.70, "experimental": 0.20, "hedge": 0.10},
            Regime.MEAN_REVERSION: {"live": 0.80, "experimental": 0.10, "hedge": 0.10},
            Regime.MICROSTRUCTURE: {"live": 0.60, "experimental": 0.30, "hedge": 0.10},
            Regime.UNCERTAIN: {"live": 0.50, "experimental": 0.20, "hedge": 0.30},
        }
        regime_alloc = allocations.get(regime, allocations[Regime.UNCERTAIN])
        return {
            account_id: total_capital * Decimal(str(regime_alloc.get(account_id, 0)))
            for account_id in accounts.keys()
        }

