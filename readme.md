# 🚀 OTQ Lite: Solana DEX Trading Bot (v1-lite)

> **Minimal. Deterministic. Local-first. For crypto-native users.**

---

## 🧑‍💻 Who Should Use This?
- 🦾 You understand wallets, RPCs, DEXs, and DeFi risk
- 🛠️ You’ve used bots/scripts before and are comfortable with CLI tools
- 🔍 You want a transparent, auditable, minimal trading system
- 📝 You’re comfortable editing environment variables and reading logs
- 🧩 You want to run and audit your own code, not trust a SaaS

---

## 🌐 What is OTQ Lite?
OTQ Lite is a **DEX-only, local-first trading system** for Solana, built for users who want:
- Full control over their funds and keys
- Deterministic, auditable execution (no hidden logic)
- A CLI-first experience (no web UI, no cloud dependencies)
- Simple, robust mean-reversion strategies
- Clear separation between live and paper trading

**No CEX support. No multi-user custody. No advanced dashboards.**

---

## ⚡ Features
- **DEX-only:** No CEX support, no custody risk
- **Local-first:** Runs on your machine, not a cloud service
- **CLI-driven:** No web UI, all interaction via terminal
- **Mean-reversion strategies:** Built-in regime model
- **Paper & live trading:** Safe defaults, explicit warnings for live mode
- **SQLite persistence:** All trades and logs are stored locally
- **Modular architecture:** Easy to audit and extend for advanced users

---

## 🏁 Quickstart

### 1️⃣ Clone and Install
```sh
git clone https://github.com/yourname/otq_lite.git
cd otq_lite
python3.11 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install .
```

### 2️⃣ Set Up Your Wallet
- **Create a new Solana keypair** (do NOT use your main wallet)
- Store it at: `~/.otq_lite_keys/otq_lite_bot.json` (or set `SOLANA_KEYPAIR_PATH`)
- See [📚 Kyzlo-Lite-Wiki.md](Kyzlo-Lite-Wiki.md) for step-by-step wallet setup
- **Why a new keypair?**
  - Keeps your main funds safe
  - Easy to rotate or revoke
  - Prevents accidental exposure of your main wallet

### 3️⃣ Configure Environment
- Copy `.env` to your own config or set variables in your shell
- **Required:**
  - `SOLANA_RPC_URL` (Helius or other Solana RPC)
  - `PHANTOM_KEYPAIR_JSON` (path to your keypair)
  - `JUPITER_API_KEY` (get from [portal.jup.ag](https://portal.jup.ag/))
- **Optional:** Adjust risk, pairs, and runtime flags as needed
- **Tip:** All config is local—no data leaves your machine except for on-chain transactions.

### 4️⃣ Run the CLI
```sh
python -m otq_lite.cli
```
- Navigate the campus-style menu: **HQ**, **Labs**, **Control Room**, **Archives**, **Settings**
- Start with **System Warmup** to validate your setup
- Use **Run (Dry-Run)** to simulate trading safely
- Only use **Run (Live)** when you are ready and have confirmed all settings

---

## 🖥️ CLI Navigation

- **Kyzlo HQ:** Live trading (mainnet). Start/stop engine, view positions, wallet, emergency stop.
- **Kyzlo Labs:** Paper trading, backtesting, devnet airdrop, strategy playground.
- **Control Room:** Monitor regime, positions, P&L, system health, and logs.
- **Archives:** View/export trade history, performance, and reports.
- **Settings:** Adjust risk, strategy, and display options.

**All actions are confirmed in the CLI. Live trading requires explicit confirmation.**

---

## ⚙️ Environment Variables

See the included `.env` file for all options and safe defaults. Key settings:

| Variable              | Purpose                        |
|-----------------------|--------------------------------|
| `SOLANA_RPC_URL`      | Your Solana RPC endpoint       |
| `PHANTOM_KEYPAIR_JSON`| Path to your keypair JSON      |
| `JUPITER_API_KEY`     | Jupiter aggregator API key     |
| `PAIR_UNIVERSE`       | Trading pairs (e.g. `SOL/USDC,JUP/USDC`) |
| `JUP_NOTIONAL_USDC`   | Trade size per position        |
| `JUP_MAX_POSITIONS`   | Max open positions             |
| `DRY_RUN`             | `true` for simulation, `false` for live |
| `DB_PATH`             | SQLite DB path (default: local)|

---

## 🛡️ Safety & Best Practices

> **⚠️ Never use your main wallet! Always generate a new keypair for the bot.**

- Keep your keypair outside the repo (`~/.otq_lite_keys/`)
- Start in dry-run mode: validate everything before risking funds
- Explicit warnings: live trading requires confirmation in the CLI
- Use **Archives** and **Control Room** for monitoring
- **Back up your keypair** and keep it secure
- **Review all code and config before running live**

---

## 🧭 How It Works

1. **Regime Model:** The bot uses a simple mean-reversion regime model to decide when to enter/exit trades.
2. **Execution:** Trades are routed via Jupiter aggregator for best price on Solana DEXs.
3. **Persistence:** All trades, logs, and performance data are stored in a local SQLite database.
4. **CLI Menus:** All actions are performed via a campus-style CLI menu system, with clear separation between live and test actions.

---

## 🆘 Troubleshooting

- ❌ **CLI fails to start?**
  - Check your Python version (3.11+ required)
  - Ensure all dependencies are installed (`pip install .`)
- ❌ **Wallet/key errors?**
  - Verify your keypair path and permissions
  - Make sure the keypair is a valid Solana JSON array
- ❌ **RPC or API issues?**
  - Check your `.env` and network connectivity
  - Ensure your RPC endpoint is working and funded for mainnet
- ❓ **Still stuck?**
  - See [Kyzlo-Lite-Wiki.md](Kyzlo-Lite-Wiki.md) for more Q&A and setup details

---

## ❓ FAQ

- **Can I use this on mainnet?**  
  Yes, but only after validating in dry-run and understanding the risks.

- **Is there a web UI?**  
  No. This is CLI-only for transparency and reliability.

- **Can I use my Phantom wallet?**  
  You must export a keypair and use it as described above.

- **What happens if I lose my keypair?**  
  You lose access to your funds. Always back up your keypair securely.

- **How do I update the bot?**  
  Pull the latest code and review the changelog. Re-run `pip install .` if dependencies change.

---

## 📄 License

MIT. Use at your own risk. No warranty. Not for beginners.

---

> **OTQ Lite is for experienced users who want full control and transparency. If you’re not comfortable with CLI tools, wallets, or DeFi risk, this project is not for you.**
