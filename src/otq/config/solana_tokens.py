"""
Solana token universe configuration for Jupiter DEX trading.

This module is intentionally small so both engines and dashboards can import
the same token metadata.

If any mint changes, update the constants below or override via a custom
config import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SolanaToken:
    symbol: str
    mint: str
    decimals: int


# NOTE: Mint addresses are the widely used mainnet mints; verify before live.
SOL = SolanaToken(symbol="SOL", mint="So11111111111111111111111111111111111111112", decimals=9)
USDC = SolanaToken(symbol="USDC", mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", decimals=6)
BONK = SolanaToken(symbol="BONK", mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", decimals=5)
TRUMP = SolanaToken(symbol="TRUMP", mint="6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN", decimals=6)
POPCAT = SolanaToken(symbol="POPCAT", mint="9E8QDCsADVjjDkbjmC8S5zaa7ZgN9sKDRTLUBXfw2g5D", decimals=6)
WIF = SolanaToken(symbol="WIF", mint="EPeUqhKcq7rVap5mpQxb38nSxr2idKdvUSsfx8bVsgcG", decimals=6)
JUP = SolanaToken(symbol="JUP", mint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", decimals=6)
MEW = SolanaToken(symbol="MEW", mint="MEWoWWWWWxvHb6GyFNR7fsCAHbLdwhUE5g1JThXqrQH", decimals=6)


TOKEN_MAP: Dict[str, SolanaToken] = {
    t.symbol: t
    for t in [SOL, USDC, BONK, TRUMP, POPCAT, WIF, JUP, MEW]
}


def load_extra_tokens(extra_tokens_str: Optional[str] = None) -> Dict[str, SolanaToken]:
    """Load extra tokens from config string (called at boot only).

    Format (comma-separated):
        "TRUMP=<mint>:<decimals>,FOO=<mint>:<decimals>"

    Returns: Updated TOKEN_MAP with extra tokens merged in.
    
    Notes:
    - Does not modify built-in tokens unless explicitly overridden.
    - Called once during load_config_or_exit(), not at runtime.
    """
    token_map = TOKEN_MAP.copy()
    
    if not extra_tokens_str:
        return token_map

    raw = extra_tokens_str.strip()
    if not raw:
        return token_map

    for entry in [p.strip() for p in raw.split(",") if p.strip()]:
        if "=" not in entry:
            continue
        sym, rest = entry.split("=", 1)
        sym = sym.strip().upper()
        rest = rest.strip()
        if not sym or not rest:
            continue
        if ":" not in rest:
            continue
        mint, dec_str = rest.split(":", 1)
        mint = mint.strip()
        dec_str = dec_str.strip()
        if not mint or not dec_str:
            continue
        try:
            decimals = int(dec_str)
        except Exception:
            continue
        token_map[sym] = SolanaToken(symbol=sym, mint=mint, decimals=decimals)
    
    return token_map

# Base/quote pairs we trade (always quote USDC for this engine)
PAIR_UNIVERSE: List[str] = [
    "SOL/USDC",
    "TRUMP/USDC",
    "POPCAT/USDC",
    "WIF/USDC",
    "JUP/USDC",
    "MEW/USDC",
]


def get_token(symbol: str) -> SolanaToken:
    key = symbol.upper()
    if key not in TOKEN_MAP:
        raise KeyError(f"Token not configured: {symbol}")
    return TOKEN_MAP[key]


def list_pairs() -> List[str]:
    return PAIR_UNIVERSE.copy()


__all__ = [
    "SolanaToken",
    "SOL",
    "USDC",
    "BONK",
    "TRUMP",
    "POPCAT",
    "WIF",
    "JUP",
    "MEW",
    "TOKEN_MAP",
    "PAIR_UNIVERSE",
    "get_token",
    "list_pairs",
    "load_extra_tokens",
]

