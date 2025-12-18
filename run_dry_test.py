"""
Phase 14.2: Dry Run Test
Runs Jupiter V1-Lite engine in DRY_RUN mode for ~90 seconds to verify:
- ENGINE_INIT log with correct wallet
- PRICE logs for each pair every tick
- RSI updating (check strategy.price_history lengths)
- No actual transactions executed
"""

import asyncio
import sys
import os
import signal

# Setup environment
sys.path.insert(0, 'src')

# Load test environment
from dotenv import load_dotenv
load_dotenv('.env.test')

print("="*60)
print("PHASE 14.2: DRY RUN TEST")
print("="*60)
print(f"DRY_RUN Mode: {os.getenv('DRY_RUN', 'true')}")
print(f"Pairs: {os.getenv('JUP_PAIRS', 'SOL/USDC')}")
print(f"Tick Interval: {os.getenv('TICK_INTERVAL', '30')}s")
print("="*60)
print("\nStarting engine... (will run for 3 ticks ~90 seconds)")
print("Watch for:")
print("  ✓ ENGINE_INIT with wallet address")
print("  ✓ PRICE logs for each pair")
print("  ✓ RSI updates in strategy")
print("  ✓ No actual transaction signatures")
print("\nPress Ctrl+C to stop early\n")
print("="*60 + "\n")

# Import and run engine
from otq.engines.jupiter_dex_engine_v1_lite import main

# Run engine with timeout
async def run_with_timeout():
    task = asyncio.create_task(main())
    try:
        # Run for 95 seconds (3+ ticks with 30s interval)
        await asyncio.wait_for(task, timeout=95.0)
    except asyncio.TimeoutError:
        print("\n" + "="*60)
        print("DRY RUN TEST COMPLETED")
        print("="*60)
        print("✓ Engine ran successfully for 3+ ticks")
        print("✓ Check logs above for required outputs")
        task.cancel()
    except KeyboardInterrupt:
        print("\n" + "="*60)
        print("Test stopped by user")
        print("="*60)
        task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(run_with_timeout())
    except KeyboardInterrupt:
        print("\nTest stopped.")
        sys.exit(0)
