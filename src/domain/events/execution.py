from dataclasses import dataclass
from decimal import Decimal

from .base import Event


@dataclass
class FillEvent(Event):
    execution_report: "ExecutionReport"
    position_delta: Decimal
    realized_pnl: Decimal

