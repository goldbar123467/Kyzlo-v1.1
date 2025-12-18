from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime


@dataclass
class PerpMetrics:
    """Perpetual futures metrics from derivative venues."""

    symbol: str
    funding_rate: Decimal
    open_interest: Decimal
    volume_24h: Decimal
    timestamp: datetime

