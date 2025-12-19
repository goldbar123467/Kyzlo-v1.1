"""
run_engine.py - Single entry point for Jupiter DEX Engine V1-Lite

CRITICAL: This file MUST be the process entry point.
Bootstrap runs once, first, before any networking imports.
"""

import sys

# Add src to path for imports
sys.path.insert(0, 'src')


def main() -> int:
    """
    Main entry point.
    
    Execution order (CRITICAL):
    1. Bootstrap network (IPv4 forcing, DNS patching)
    2. Import engine module (after bootstrap)
    3. Run async main loop
    4. Return exit code
    """
    # MUST be first - before anything that might import httpx/solana/etc.
    from otq.engines.execution.state.infrastucture.network_bootstrap import bootstrap_network
    bootstrap_network()
    
    # Only after bootstrap is safe to import networking code
    import asyncio
    from otq.engines.jupiter_dex_engine_v1_lite import main as engine_main
    
    # Run the async engine
    asyncio.run(engine_main())
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
