from dataclasses import dataclass

from .base import Event


@dataclass
class TickEvent(Event):
    symbol: str
    market_state: "MarketState"

