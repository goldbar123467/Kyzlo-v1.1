from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class ZombieOrder:
    order: "Order"
    marked_at: datetime
    reason: str
    received_fills: List["ExecutionReport"] = field(default_factory=list)


@dataclass
class FillHandlingResult:
    action: str
    fill: "ExecutionReport"
    order: Optional["Order"]
    position_update: Optional["Position"] = None
    alert: Optional[str] = None


class StaleFillHandler:
    """Handles fills for timed-out or unknown orders."""

    def __init__(self, zombie_ttl_seconds: float = 300.0):
        self.zombie_ttl_seconds = zombie_ttl_seconds
        self._zombie_orders: Dict[str, ZombieOrder] = {}

    def mark_zombie(self, order: "Order", reason: str):
        self._zombie_orders[order.id] = ZombieOrder(
            order=order, marked_at=datetime.utcnow(), reason=reason
        )

    def handle_fill(self, fill, order_manager, portfolio_manager) -> FillHandlingResult:
        order = order_manager.get_order(fill.order_id)
        if order is not None:
            return FillHandlingResult(action="NORMAL", fill=fill, order=order)

        zombie = self._zombie_orders.get(fill.order_id)
        if zombie is not None:
            zombie.received_fills.append(fill)
            position = portfolio_manager.apply_fill(fill, zombie.order)
            return FillHandlingResult(
                action="ZOMBIE_FILL",
                fill=fill,
                order=zombie.order,
                position_update=position,
                alert="Fill for timed-out order",
            )

        return FillHandlingResult(
            action="UNKNOWN_FILL",
            fill=fill,
            order=None,
            alert="CRITICAL: Fill for unknown order",
        )

