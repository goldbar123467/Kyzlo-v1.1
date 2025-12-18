from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Price:
    """Monetary price value object with positivity guard."""
    value: Decimal

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError("Price must be positive")


@dataclass(frozen=True)
class Quantity:
    """Signed quantity (can be negative for shorts)."""
    value: Decimal

    def __post_init__(self):
        if self.value == 0:
            raise ValueError("Quantity cannot be zero")


@dataclass(frozen=True)
class Notional:
    """Notional amount; must be non-negative."""
    value: Decimal

    def __post_init__(self):
        if self.value < 0:
            raise ValueError("Notional cannot be negative")

