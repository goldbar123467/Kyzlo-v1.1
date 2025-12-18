from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime

from .base import TradingStrategy
from ..events.signal import Signal
from ..models.regime import Regime


class EnsembleStrategy(TradingStrategy):
    """Combines multiple models based on regime."""

    def __init__(
        self,
        models: Dict[Regime, List[TradingStrategy]],
        weights: Dict[Regime, List[float]],
    ):
        self.models = models
        self.weights = weights

    def generate_signal(
        self,
        market_state: "MarketState",
        portfolio: "Portfolio",
        regime: Regime = None,
    ) -> Optional[Signal]:
        regime = regime or Regime.UNCERTAIN
        active_models = self.models.get(regime, [])
        model_weights = self.weights.get(regime, [1.0] * len(active_models))

        if not active_models:
            return None

        signals = []
        for model in active_models:
            sig = model.generate_signal(market_state, portfolio)
            if sig:
                signals.append(sig)

        if not signals:
            return None

        total_weight = sum(model_weights[: len(signals)])
        weighted_position = (
            sum(float(sig.target_position) * w for sig, w in zip(signals, model_weights))
            / total_weight
            if total_weight > 0
            else 0
        )
        avg_confidence = sum(sig.confidence for sig in signals) / len(signals)

        return Signal(
            strategy_id="ensemble",
            symbol=market_state.symbol,
            target_position=Decimal(str(round(weighted_position, 2))),
            confidence=avg_confidence,
            timestamp=datetime.utcnow(),
            metadata={
                "regime": regime.value,
                "component_signals": len(signals),
                "weights": model_weights[: len(signals)],
            },
        )

