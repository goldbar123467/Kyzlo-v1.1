# src/otq/strategies/base.py
from abc import ABC, abstractmethod
import torch
import pandas as pd
from typing import Dict, Any, Tuple, Union

class Strategy(ABC):
    """
    Abstract Base Class for all OTQ Strategies.
    Enforces a strict interface for signal generation and state management.
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        # Auto-detect GPU
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    @abstractmethod
    def calculate_signals(self, market_data: pd.DataFrame) -> Union[torch.Tensor, Tuple[torch.Tensor, Any, Any]]:
        """
        Core Logic: Input Market Data -> Output Buy/Sell/Hold Signals.
        Must return a GPU Tensor of signals (1=Buy, -1=Sell, 0=Hold).
        """
        pass

    def to_gpu(self, data: pd.DataFrame) -> torch.Tensor:
        """Helper to move Pandas data to GPU Tensor efficiently."""
        return torch.tensor(data.values, dtype=torch.float32, device=self.device)

    def describe(self):
        print(f"🧠 Strategy: {self.name}")
        print(f"   ⚙️ Config: {self.config}")
        print(f"   🚀 Device: {self.device}")