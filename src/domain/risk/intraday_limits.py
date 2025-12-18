from decimal import Decimal
from typing import Dict


class IntradayRiskLimits:
    """Runtime risk monitoring."""

    def check_account_drawdown(
        self,
        account: "LogicalAccount",
        portfolio: "Portfolio",
    ) -> bool:
        account_value = portfolio.total_value * account.capital_pct
        drawdown = (account.initial_capital - account_value) / account.initial_capital
        return drawdown < account.max_drawdown

    def check_strategy_drawdown(
        self,
        strategy_id: str,
        pnl_tracker: Dict[str, Decimal],
        max_strategy_loss: Decimal,
    ) -> bool:
        strategy_pnl = pnl_tracker.get(strategy_id, Decimal("0"))
        return strategy_pnl > -max_strategy_loss

    def check_volatility_regime(
        self,
        market_state: "MarketState",
        vol_threshold: float = 0.5,
    ) -> float:
        vol = float(market_state.vol_estimate)
        if vol > vol_threshold:
            return max(0.2, 1.0 - (vol - vol_threshold) / vol_threshold)
        return 1.0

