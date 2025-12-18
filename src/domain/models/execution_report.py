from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from .order import OrderStatus


@dataclass
class ExecutionReport:
    """Venue-agnostic fill/cancel/reject notification."""

    order_id: str
    venue_order_id: str
    venue_fill_id: str
    timestamp: datetime
    status: OrderStatus
    filled_qty: Decimal
    remaining_qty: Decimal
    avg_fill_price: Optional[Decimal]
    fee: Optional[Decimal]
    fee_currency: Optional[str]
    venue_id: str
    sequence_number: int
    is_final: bool
    raw_message: Dict[str, Any]
    venue_timestamp: datetime
    liquidity_flag: Optional[str] = None  # "MAKER" or "TAKER"

