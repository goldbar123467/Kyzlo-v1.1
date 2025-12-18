# Kyzlo v1.1

A Solana DEX trading bot using Jupiter aggregator with trend-pullback scalping strategies.

## Overview

Kyzlo v1.1 implements a trading engine for Solana DEX markets through the Jupiter aggregator. It includes:

* **Kyzlo Bots**: Automated trading on Solana DEX markets via Jupiter
* **Trend-Pullback Strategy**: Mean reversion scalping strategy
* **CLI Interface**: Command-line based operation
* **Risk Management**: Position sizing, slippage controls, max hold time
* **Testing Suite**: Comprehensive unit and integration tests

## Project Structure
```
src/
  otq/
    engines/         # Kyzlo Bot implementations
    strategies/      # Trading strategies
    adapters/        # Market data and broker adapters
    domain/          # Domain models and types
    risk/            # Risk management
tests/               # Test suite
config/              # Configuration files (jupiter.toml)
scripts/             # Testing and utility scripts
```

## Requirements

* **Python**: 3.11+
* **Solana RPC**: Mainnet or Devnet endpoint
* **Jupiter API**: API access (optional)

## Installation
```bash
# Create virtual environment
python3.11 -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Configuration

Edit `config/jupiter.toml` to configure:

* **Trading pairs**: `instruments = ["SOL", "JUP", "TRUMP"]`
* **Risk limits**: Max position size, slippage, hold time
* **Strategy parameters**: RSI thresholds, bar intervals
* **RPC endpoint**: Solana mainnet/devnet URL

## Running Tests
```bash
# Run Kyzlo Bot engine tests
python test_jupiter_v1_lite.py

# Run strategy tests
pytest tests/test_jupiter_trend_pullback_scalper.py

# Run all tests
pytest tests/
```

## Usage

### Strategy Testing
```bash
# Test strategy with synthetic data
python scripts/smoke_jupiter_trend_pullback.py
```

### Running Kyzlo Bots
```bash
# Entry point defined in pyproject.toml
kyzlo-engine

# Or run directly
python -m otq.engines.jupiter_dex_engine_v1_lite
```

## Key Features

* **Jupiter Integration**: Uses Jupiter aggregator for best execution
* **Solana Native**: Built on Solana SDK with proper keypair handling
* **Configurable Strategy**: Trend-pullback scalper with adjustable parameters
* **Risk Controls**: Position limits, slippage protection, time-based exits
* **SQLite Persistence**: Local database for trade history
* **CLI-Based**: Simple command-line interface for testing and execution

## Safety Notes

⚠️ **This is trading software. Use at your own risk.**

* Start with small position sizes
* Test thoroughly on devnet first
* Never commit private keys to git
* Store keypairs securely outside the repository
* Review all configuration before trading live

## Development
```bash
# Run linter
ruff check src/

# Format code
ruff format src/

# Type checking
mypy src/
```

## License

© Kyzlo Labs. See project license file.
