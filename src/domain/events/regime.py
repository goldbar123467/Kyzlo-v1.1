from dataclasses import dataclass

from .base import Event


@dataclass
class RegimeChangeEvent(Event):
    old_regime: "Regime"
    new_regime: "Regime"
    confidence: float

