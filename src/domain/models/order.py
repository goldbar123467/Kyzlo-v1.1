from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class OrderStatus(Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


OrderId = str  # Type alias for clarity


@dataclass
class Order:
    id: OrderId
    symbol: str
    side: Side
    qty: Decimal
    order_type: OrderType
    status: OrderStatus
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    created_at: datetime
    last_update_at: datetime
    account_id: str  # maps to LogicalAccount
    time_in_force: str = "DAY"
    client_order_id: Optional[str] = None
    venue_order_id: Optional[str] = None

