<p align="center">
  <img src="https://img.shields.io/badge/KYZLO-v1.1-blueviolet?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyTDIgNy4wMDAxVjE3TDEyIDIyTDIyIDE3VjcuMDAwMUwxMiAyWiIvPjwvc3ZnPg==" alt="Kyzlo v1.1"/>
  <img src="https://img.shields.io/badge/Solana-Powered-9945FF?style=for-the-badge&logo=solana&logoColor=white" alt="Solana"/>
  <img src="https://img.shields.io/badge/Jupiter-Aggregator-6B5CE7?style=for-the-badge" alt="Jupiter"/>
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License"/>
</p>

<div align="center">
```
██╗  ██╗██╗   ██╗███████╗██╗      ██████╗ 
██║ ██╔╝╚██╗ ██╔╝╚══███╔╝██║     ██╔═══██╗
█████╔╝  ╚████╔╝   ███╔╝ ██║     ██║   ██║
██╔═██╗   ╚██╔╝   ███╔╝  ██║     ██║   ██║
██║  ██╗   ██║   ███████╗███████╗╚██████╔╝
╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝ ╚═════╝ 
            ━━━ L A B S ━━━
```

**Autonomous DEX Trading Infrastructure for Solana**

[Getting Started](#-installation) · [Documentation](#-usage) · [Contributing](#-development)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

</div>

## 🌌 Overview

Kyzlo v1.1 is institutional-grade trading infrastructure for Solana DEX markets, powered by Jupiter aggregator. Built for speed, reliability, and precision execution.

| Feature | Description |
|---------|-------------|
| 🤖 **Kyzlo Bots** | Automated trading engines for Solana DEX |
| 📈 **Trend-Pullback** | Mean reversion scalping strategies |
| 🛡️ **Risk Management** | Position sizing, slippage controls, max hold time |
| ⚡ **Jupiter Integration** | Best-in-class execution via aggregation |

## 📁 Architecture
```
src/
├── otq/
│   ├── engines/         # 🤖 Kyzlo Bot implementations
│   ├── strategies/      # 📊 Trading strategies
│   ├── adapters/        # 🔌 Market data & broker adapters
│   ├── domain/          # 🏗️  Domain models & types
│   └── risk/            # 🛡️  Risk management
tests/                   # ✅ Test suite
config/                  # ⚙️  Configuration (jupiter.toml)
scripts/                 # 🔧 Utilities
```

## 📋 Requirements
```yaml
Python:      3.11+
Solana RPC:  Mainnet or Devnet endpoint
Jupiter:     API access (optional)
```

## 🚀 Installation
```bash
# Create virtual environment
python3.11 -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install Kyzlo
pip install -e .
```

## ⚙️ Configuration

Edit `config/jupiter.toml`:
```toml
# Trading pairs
instruments = ["SOL", "JUP", "TRUMP"]

# Risk limits, strategy params, RPC endpoint
# See config file for full options
```

## 🧪 Testing
```bash
# Kyzlo Bot engine tests
python test_jupiter_v1_lite.py

# Strategy tests
pytest tests/test_jupiter_trend_pullback_scalper.py

# Full suite
pytest tests/
```

## 💫 Usage

**Strategy Testing**
```bash
python scripts/smoke_jupiter_trend_pullback.py
```

**Running Kyzlo Bots**
```bash
kyzlo-engine
# or: python -m otq.engines.jupiter_dex_engine_v1_lite
```

## ⚠️ Safety

> **This is trading software. Use at your own risk.**

- Start with small position sizes
- Test thoroughly on devnet first  
- Never commit private keys
- Store keypairs securely outside repo

## 🔧 Development
```bash
ruff check src/    # Lint
ruff format src/   # Format
mypy src/          # Type check
```

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

<div align="center">

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Built with 💜 by [Kyzlo Labs](https://github.com/kyzlo-labs)**

<sub>Solana • Jupiter • DeFi</sub>

</div>
