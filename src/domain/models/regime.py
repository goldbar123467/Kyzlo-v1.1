from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict


class Regime(Enum):
    TREND = "TREND"
    MEAN_REVERSION = "MEAN_REVERSION"
    MICROSTRUCTURE = "MICROSTRUCTURE"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class RegimeState:
    current: Regime
    confidence: float
    transition_probs: Dict[Regime, float]
    features: Dict[str, float]
    last_update: datetime

