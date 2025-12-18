from dataclasses import dataclass

from .base import Event


@dataclass
class OrderEvent(Event):
    order: "Order"
    reason: str  # "SIGNAL" | "RISK_ADJUST" | "REBALANCE"

