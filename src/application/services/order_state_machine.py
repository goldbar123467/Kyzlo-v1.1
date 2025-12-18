from datetime import datetime
from typing import Dict

from ...domain.models.order import Order, OrderStatus


class InvalidTransition(Exception):
    """Raised when an invalid order state transition is attempted."""


class OrderStateMachine:
    """Tracks order lifecycle with explicit transition rules."""

    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self._transitions = {
            OrderStatus.NEW: {OrderStatus.PENDING, OrderStatus.REJECTED, OrderStatus.CANCELED},
            OrderStatus.PENDING: {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.CANCELED},
            OrderStatus.SUBMITTED: {
                OrderStatus.FILLED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.REJECTED,
                OrderStatus.CANCELED,
            },
            OrderStatus.PARTIALLY_FILLED: {OrderStatus.FILLED, OrderStatus.CANCELED},
        }

    def add_order(self, order: Order):
        """Add order to tracking."""
        self.orders[order.id] = order

    def can_transition(self, order_id: str, to_state: OrderStatus) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False
        current = order.status
        valid_next = self._transitions.get(current, set())
        return to_state in valid_next

    def transition(self, order_id: str, to_state: OrderStatus) -> Order:
        """Execute state transition."""
        if not self.can_transition(order_id, to_state):
            order = self.orders.get(order_id)
            current = order.status if order else "UNKNOWN"
            raise InvalidTransition(f"{current} -> {to_state}")

        order = self.orders[order_id]
        order.status = to_state
        order.last_update_at = datetime.utcnow()
        return order

