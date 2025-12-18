from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from otq.domain.perps.health import MarginState
from otq.domain.perps.orders import OrderAckOrFill, OrderIntent
from otq.domain.perps.types import PerpsPosition


class PerpsBrokerError(RuntimeError):
    pass


class InsufficientMargin(PerpsBrokerError):
    pass


class ReduceOnlyViolation(PerpsBrokerError):
    pass


class CapabilityViolation(PerpsBrokerError):
    pass


@dataclass(frozen=True)
class VenueCapabilities:
    supports_reduce_only: bool
    supports_protective_limits: bool
    min_size: float = 0.0
    min_notional: float = 0.0
    tick_size: float = 0.0
    step_size: float = 0.0
    max_leverage_venue: float = 1.0


class PerpsBrokerPort(ABC):
    """Perps execution abstraction.

    No venue-specific objects leak out. Every order attempt returns an OrderAckOrFill.
    """

    @abstractmethod
    def get_positions(self) -> List[PerpsPosition]:
        ...

    @abstractmethod
    def get_margin_state(self) -> MarginState:
        ...

    @abstractmethod
    def get_capabilities(self) -> Dict[str, VenueCapabilities]:
        ...

    @abstractmethod
    def cancel_orders(self, symbol: str) -> bool:
        ...

    @abstractmethod
    def open_position(self, intent: OrderIntent) -> OrderAckOrFill:
        ...

    @abstractmethod
    def reduce_position(self, intent: OrderIntent) -> OrderAckOrFill:
        ...

    @abstractmethod
    def close_position(self, intent: OrderIntent) -> OrderAckOrFill:
        ...
