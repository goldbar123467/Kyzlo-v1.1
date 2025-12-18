"""Evaluation-only harness for the OTQ PortfolioManager / Router.

This script does NOT place any orders. It builds a few synthetic candidates,
runs them through the router, and prints the resulting decision(s) plus
blocked-reason summaries.

Usage:
  python scripts/test_router.py
  python scripts/test_router.py --audit-path logs/router_audit.jsonl
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root without installing the package
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from otq.portfolio import PortfolioManager, PortfolioManagerConfig, PortfolioState
from otq.portfolio.types import CandidateAction, PositionRecord


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-path", default=None, help="Optional JSONL audit path")
    args = ap.parse_args()

    cfg = PortfolioManagerConfig(
        enabled_venues={"binanceus", "jupiter"},
        strategy_priority=["binanceus_crypto_mr", "jupiter_mr"],
        max_positions_total=2,
        max_exposure_per_asset=5_000.0,
        allow_multi_venue_exposure=False,
        max_venues_per_symbol=1,
        decision_audit_path=args.audit_path,
    )

    pm = PortfolioManager(cfg)
    state = PortfolioState()

    # Simulate an existing BTC position on Binance.US
    state.add_position(
        PositionRecord(
            venue="binanceus",
            instrument="BTC/USD",
            base_asset="BTC",
            quote_asset="USD",
            side="buy",
            notional=2_500.0,
            opened_at=_now(),
            strategy_id="binanceus_crypto_mr",
        )
    )

    # Two venues propose SOL at the same time; router should pick deterministically.
    instrument = "SOL/USDC"
    candidates = [
        CandidateAction(
            strategy_id="jupiter_mr",
            venue="jupiter",
            instrument=instrument,
            base_asset="SOL",
            quote_asset="USDC",
            side="buy",
            notional=1_000.0,
            timestamp=_now(),
            score=0.25,
            info={"regime": "trend"},
        ),
        CandidateAction(
            strategy_id="binanceus_crypto_mr",
            venue="binanceus",
            instrument="SOL/USD",
            base_asset="SOL",
            quote_asset="USD",
            side="buy",
            notional=1_000.0,
            timestamp=_now(),
            score=0.10,
            info={"regime": "trend"},
        ),
    ]

    chosen = pm.evaluate_instrument(instrument, candidates, state, _now())
    print("Decision 1:")
    print(f"  chosen={chosen.key() if chosen else None}")

    # Second decision: blocked (no candidates)
    pm.evaluate_instrument("ETH/USDC", [], state, _now())

    # Third decision: rejected by policy (one-net-position-by-asset across venues)
    state.add_position(
        PositionRecord(
            venue="binanceus",
            instrument="SOL/USD",
            base_asset="SOL",
            quote_asset="USD",
            side="buy",
            notional=1_000.0,
            opened_at=_now(),
            strategy_id="binanceus_crypto_mr",
        )
    )
    pm.evaluate_instrument(
        "SOL/USDC",
        [
            CandidateAction(
                strategy_id="jupiter_mr",
                venue="jupiter",
                instrument="SOL/USDC",
                base_asset="SOL",
                quote_asset="USDC",
                side="buy",
                notional=500.0,
                timestamp=_now(),
                info={"regime": "trend"},
            )
        ],
        state,
        _now(),
    )

    print("\nTop blockers:")
    for reason, count, pct in pm.blocked.get_top_blockers_pct(10):
        print(f"  {reason}: {count} ({pct:.1f}%)")

    print("\nBy venue:")
    for venue, counts in pm.blocked.get_venue_analysis().items():
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        print(f"  {venue}: {top}")

    pm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
