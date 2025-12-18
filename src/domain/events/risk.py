from dataclasses import dataclass
from typing import Dict, Any

from .base import Event


@dataclass
class RiskBlockEvent(Event):
    signal: "Signal"
    rule_name: str
    reason: str
    parameters: Dict[str, Any]

