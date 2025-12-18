from datetime import datetime
from typing import Dict, List, Optional
import uuid

from ..application.services.order_state_machine import OrderStateMachine
from ..domain.models.order import Order, OrderStatus, OrderType, Side


class InvalidOrderTransition(Exception):
    """Raised when OMS transition is invalid."""


class OrderManager:
    """Central OMS authority for orders."""

    def __init__(self, fsm: OrderStateMachine, persistence=None):
        self.fsm = fsm
        self.persistence = persistence
        self._orders: Dict[str, Order] = {}

    def create_order(self, signal: "Signal", account_id: str) -> Order:
        """Create order from approved signal."""
        order = Order(
            id=str(uuid.uuid4()),
            symbol=signal.symbol,
            side=Side.BUY if signal.target_position > 0 else Side.SELL,
            qty=abs(signal.target_position),
            order_type=OrderType.MARKET,
            status=OrderStatus.NEW,
            limit_price=None,
            stop_price=None,
            created_at=datetime.utcnow(),
            last_update_at=datetime.utcnow(),
            account_id=account_id,
        )
        self._orders[order.id] = order
        self.fsm.add_order(order)
        return order

    def transition_order(
        self, order_id: str, new_status: OrderStatus, venue_order_id: Optional[str] = None
    ) -> Order:
        """State transition with validation."""
        if not self.fsm.can_transition(order_id, new_status):
            current = self._orders.get(order_id)
            raise InvalidOrderTransition(
                f"Cannot transition {current.status if current else 'UNKNOWN'} -> {new_status}"
            )
        order = self.fsm.transition(order_id, new_status)
        if venue_order_id:
            order.venue_order_id = venue_order_id
        # Persistence hook (async in real impl)
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def get_open_orders(self) -> List[Order]:
        terminal = {
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }
        return [o for o in self._orders.values() if o.status not in terminal]

