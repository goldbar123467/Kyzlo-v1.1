<div align="center">

```
╔══════════════════════════════════════════════════╗
║                                                  ║
║    ██╗  ██╗██╗   ██╗███████╗██╗      ██████╗     ║
║    ██║ ██╔╝╚██╗ ██╔╝╚══███╔╝██║     ██╔═══██╗    ║
║    █████╔╝  ╚████╔╝   ███╔╝ ██║     ██║   ██║    ║
║    ██╔═██╗   ╚██╔╝   ███╔╝  ██║     ██║   ██║    ║
║    ██║  ██╗   ██║   ███████╗███████╗╚██████╔╝    ║
║    ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝ ╚═════╝     ║
║                          L A B S                 ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

**Autonomous DEX Trading Infrastructure for Solana**

[![Kyzlo](https://img.shields.io/badge/KYZLO-v1.1-8B5CF6?style=for-the-badge)](https://github.com/kyzlo-labs)
[![Solana](https://img.shields.io/badge/SOLANA-Powered-9945FF?style=for-the-badge&logo=solana&logoColor=white)](https://solana.com)
[![Jupiter](https://img.shields.io/badge/JUPITER-Aggregator-4F46E5?style=for-the-badge)](https://jup.ag)
[![License](https://img.shields.io/badge/LICENSE-MIT-3B82F6?style=for-the-badge)](LICENSE)

---

[Overview](#overview) · [Installation](#installation) · [Configuration](#configuration) · [Usage](#usage) · [Development](#development)

</div>

---

## Overview

Kyzlo v1.1 delivers institutional-grade trading infrastructure for Solana DEX markets through Jupiter aggregator. Kyzlo Bots execute trend-pullback scalping strategies with precision risk management.

**Core Components**

- **Kyzlo Bots** — Automated trading engines for Solana DEX markets
- **Trend-Pullback Strategy** — Mean reversion scalping with configurable parameters
- **Risk Management** — Position sizing, slippage controls, max hold time
- **Testing Suite** — Comprehensive unit and integration tests

---

## Architecture

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

---

## Requirements

- **Python** 3.11+
- **Solana RPC** Mainnet or Devnet endpoint
- **Jupiter API** access (optional)

---

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

---

## Configuration

Edit `config/jupiter.toml` to configure trading pairs, risk limits, strategy parameters, and RPC endpoints.

```toml
instruments = ["SOL", "JUP", "TRUMP"]
```

---

## Testing

```bash
# Run Kyzlo Bot engine tests
python test_jupiter_v1_lite.py

# Run strategy tests
pytest tests/test_jupiter_trend_pullback_scalper.py

# Run all tests
pytest tests/
```

---

## Usage

**Strategy Testing**
```bash
python scripts/smoke_jupiter_trend_pullback.py
```

**Running Kyzlo Bots**
```bash
# Entry point
kyzlo-engine

# Or run directly
python -m otq.engines.jupiter_dex_engine_v1_lite
```

---

## Key Features

| Feature | Description |
|:--------|:------------|
| Jupiter Integration | Best execution via Jupiter aggregator |
| Solana Native | Built on Solana SDK with proper keypair handling |
| Configurable Strategy | Trend-pullback scalper with adjustable parameters |
| Risk Controls | Position limits, slippage protection, time-based exits |
| SQLite Persistence | Local database for trade history |

---

## Safety

> ⚠️ **This is trading software. Use at your own risk.**

- Start with small position sizes
- Test thoroughly on devnet first
- Never commit private keys to git
- Store keypairs securely outside the repository
- Review all configuration before trading live

---

## Development

```bash
ruff check src/      # Lint
ruff format src/     # Format
mypy src/            # Type check
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built by Kyzlo Labs**

`solana` · `jupiter` · `defi`

</div>
