from __future__ import annotations

"""Quick local smoke for the trend+pullback scalper logic.

This does NOT place any trades. It just feeds synthetic prices and prints signals.

Usage:
  & "C:/Users/Clark/Desktop/Stock Bot 4/.venv/Scripts/python.exe" scripts/smoke_jupiter_trend_pullback.py
"""

from otq.strategies.jupiter_trend_pullback_scalper import JupiterTrendPullbackScalper


def main() -> int:
    s = JupiterTrendPullbackScalper()
    pair = "TRUMP/USDC"

    # Uptrend then pullback
    for p in [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]:
        s.record_price(pair, p)

    for p in [109.5, 108.8, 107.8, 107.0]:
        s.record_price(pair, p)

    sig, meta = s.generate_entry_signal(pair)
    print(f"signal={sig} meta={meta}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
