from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class PreTradeCheck:
    passed: bool
    reason: Optional[str]
    rule_name: str


class PreTradeRules:
    """Checks before order submission."""

    def check_position_limit(
        self,
        signal: "Signal",
        position: Optional["Position"],
        max_size: Decimal,
    ) -> PreTradeCheck:
        current = position.quantity if position else Decimal("0")
        proposed = current + signal.target_position
        if abs(proposed) > max_size:
            return PreTradeCheck(
                passed=False,
                reason=f"Position {proposed} exceeds max {max_size}",
                rule_name="POSITION_LIMIT",
            )
        return PreTradeCheck(passed=True, reason=None, rule_name="POSITION_LIMIT")

    def check_leverage(
        self,
        signal: "Signal",
        portfolio: "Portfolio",
        account: "LogicalAccount",
        current_price: Decimal,
    ) -> PreTradeCheck:
        notional = abs(signal.target_position) * current_price
        account_capital = portfolio.total_value * account.capital_pct
        leverage = notional / account_capital if account_capital > 0 else Decimal("999")
        if leverage > account.max_leverage:
            return PreTradeCheck(
                passed=False,
                reason=f"Leverage {leverage:.2f} exceeds max {account.max_leverage}",
                rule_name="LEVERAGE",
            )
        return PreTradeCheck(passed=True, reason=None, rule_name="LEVERAGE")

    def check_fat_finger(
        self,
        signal: "Signal",
        market_state: "MarketState",
        multiplier: float = 10.0,
    ) -> PreTradeCheck:
        adv = market_state.features.get("adv", 1_000_000)
        if float(abs(signal.target_position)) > adv * 0.1:
            return PreTradeCheck(
                passed=False,
                reason=f"Order size {signal.target_position} exceeds 10% ADV",
                rule_name="FAT_FINGER",
            )
        return PreTradeCheck(passed=True, reason=None, rule_name="FAT_FINGER")

    def check_notional_limit(
        self,
        signal: "Signal",
        price: Decimal,
        max_notional: Decimal,
    ) -> PreTradeCheck:
        notional = abs(signal.target_position) * price
        if notional > max_notional:
            return PreTradeCheck(
                passed=False,
                reason=f"Notional {notional} exceeds max {max_notional}",
                rule_name="NOTIONAL_LIMIT",
            )
        return PreTradeCheck(passed=True, reason=None, rule_name="NOTIONAL_LIMIT")

