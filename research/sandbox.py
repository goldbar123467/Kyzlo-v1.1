from datetime import datetime
from typing import List

from src.application.backtest.fill_simulator import BacktestFillSimulator
from src.domain.fill_models.slippage import AlmgrenChrissSlippage, SlippageConfig
from src.domain.models.portfolio import Portfolio
from src.domain.models.market_state import MarketState


class Sandbox:
    """Notebook-friendly sandbox for quick strategy iteration."""

    def __init__(self, strategies: List["TradingStrategy"], symbols: List[str]):
        self.strategies = strategies
        self.symbols = symbols
        self.slippage_model = AlmgrenChrissSlippage()
        self.slippage_config = SlippageConfig()
        self.fill_simulator = BacktestFillSimulator(self.slippage_model, realism_level="REALISTIC")

    def backtest(self, start: str, end: str):
        """Placeholder backtest: initializes portfolio and runs strategy hooks on empty data."""
        _ = datetime.fromisoformat(start)
        _ = datetime.fromisoformat(end)
        portfolio = Portfolio.initialize(initial_capital=self.slippage_config.fixed_bps * 0 + 100000)  # simple init
        # This is intentionally lightweight; real data loading belongs in production backtest pipeline.
        return {"portfolio": portfolio, "results": []}

    def plot(self):
        """Placeholder plot hook for notebooks."""
        try:
            import matplotlib.pyplot as plt  # type: ignore
        except Exception:
            return None
        fig, ax = plt.subplots()
        ax.set_title("Sandbox placeholder")
        ax.plot([0, 1], [0, 1])
        return fig

