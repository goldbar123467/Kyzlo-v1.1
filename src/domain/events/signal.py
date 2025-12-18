from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from .base import Event


@dataclass
class Signal:
    """Model output - what we want to do."""

    strategy_id: str
    symbol: str
    target_position: Decimal
    confidence: float
    timestamp: datetime
    metadata: Dict[str, Any]
    account_id: str = "live"


@dataclass
class SignalEvent(Event):
    signal: Signal

