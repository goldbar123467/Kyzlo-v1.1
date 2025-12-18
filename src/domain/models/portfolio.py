from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict


@dataclass
class Portfolio:
    accounts: Dict[str, "LogicalAccount"]
    positions: Dict[str, "Position"]
    cash: Decimal
    total_value: Decimal
    daily_pnl: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    last_sync: datetime

    @classmethod
    def initialize(cls, initial_capital: Decimal) -> "Portfolio":
        return cls(
            accounts={},
            positions={},
            cash=initial_capital,
            total_value=initial_capital,
            daily_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            last_sync=datetime.utcnow(),
        )

