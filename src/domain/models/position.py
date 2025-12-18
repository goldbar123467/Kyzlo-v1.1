from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Position:
    symbol: str
    quantity: Decimal  # positive = long, negative = short
    avg_entry_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    last_updated: datetime
    account_id: str

    def update(self, fill_qty: Decimal, fill_price: Decimal):
        """Update position from a fill."""
        if self.quantity == Decimal("0"):
            self.avg_entry_price = fill_price
            self.quantity = fill_qty
        elif (self.quantity > 0 and fill_qty > 0) or (self.quantity < 0 and fill_qty < 0):
            total_cost = self.quantity * self.avg_entry_price + fill_qty * fill_price
            self.quantity += fill_qty
            self.avg_entry_price = total_cost / self.quantity
        else:
            self.quantity += fill_qty
            if abs(self.quantity) < Decimal("0.0001"):
                self.quantity = Decimal("0")

        self.last_updated = datetime.utcnow()

