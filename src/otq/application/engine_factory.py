"""Factory helpers for optional engines (Jupiter/Solana/Binance).

These are lightweight stubs to keep multi-engine launches working even when
the full implementations are not present. Each builder returns a simple engine
with start/stop methods that log and exit quickly.
"""

from otq.engines.binance_mr_engine import BinanceMREngine
from otq.engines.jupiter_mr_engine import JupiterMREngine
from otq.engines.solana_ot_movers_engine import SolanaOTMoversEngine
from otq.engines.solana_bridge_engine import SolanaBridgeEngine


def build_jupiter_mr_engine(paper: bool = True, config=None):
    return JupiterMREngine(paper=paper, config=config or {})


def build_solana_ot_movers_engine(paper: bool = True):
    return SolanaOTMoversEngine(paper=paper)


def build_solana_bridge_engine(paper: bool = True):
    return SolanaBridgeEngine(paper=paper)





