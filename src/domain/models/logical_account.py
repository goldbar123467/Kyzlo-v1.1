from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class AccountRole(Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    LIVE = "LIVE"
    HEDGE = "HEDGE"


@dataclass
class LogicalAccount:
    """Venue-agnostic capital bucket."""

    id: str
    role: AccountRole
    max_drawdown: Decimal
    max_leverage: Decimal
    capital_pct: Decimal
    risk_multiplier: float = 1.0
    venue_type: Optional[str] = None
    initial_capital: Decimal = Decimal("0")

