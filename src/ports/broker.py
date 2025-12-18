from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class OrderAck:
    """Acknowledgment from venue after order submission."""

    order_id: str
    venue_order_id: str
    status: str  # "SUBMITTED", "REJECTED", "DUPLICATE"
    message: str = ""


@dataclass
class Account:
    """Venue account info."""

    id: str
    buying_power: Decimal
    equity: Decimal
    cash: Decimal


class BrokerPort(ABC):
    """Execution venue abstraction."""

    @abstractmethod
    async def submit_order(self, order: "Order") -> OrderAck:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    async def get_positions(self) -> List["Position"]:
        ...

    @abstractmethod
    async def get_account(self) -> Account:
        ...

    @abstractmethod
    async def get_open_orders(self) -> List["Order"]:
        ...

