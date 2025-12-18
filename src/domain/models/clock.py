from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum


class SessionType(Enum):
    PRE = "PRE"
    REGULAR = "REGULAR"
    POST = "POST"
    CLOSED = "CLOSED"


@dataclass
class Clock:
    """Explicit time model for deterministic backtests."""

    now: datetime
    session: SessionType
    bar_index: int
    trading_day: date

