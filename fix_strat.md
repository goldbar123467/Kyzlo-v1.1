Below is a **clean, executable `agent.md`** you can drop at the **repo root**.
It is written as an **agent build plan**, phased, deterministic, and scoped strictly to **fixing the strategy numbers and deleting junk** — nothing else.

No philosophy. No optional steps. This is meant to *run you*, not inspire you.

---

# 🧠 agent.md

## JUPITER DEX ENGINE V1-LITE — STRATEGY FIX & SIMPLIFICATION AGENT

### PURPOSE

This agent exists to **repair strategy parameters, simplify strategy logic, and remove unused code paths** so the engine can trade profitably with **$10 notional** under current US-session crypto market conditions.

This agent **does not**:

* Add new features
* Add indicators
* Refactor architecture
* Improve performance
* Touch execution, oracle, or risk layers

Its sole mandate is **parameter correction + deletion**.

---

## GLOBAL CONSTRAINTS (NON-NEGOTIABLE)

* Notional per trade: **$10**
* Timeframe: **1m**
* RSI length: **14**
* RSI signal requirement: **1 tick only**
* Entry threshold (both strategies): **RSI ≤ 31**
* No additional confirmations
* No new config flags
* No new files

---

## PHASE 0 — BASELINE LOCK (DO FIRST)

### Objective

Ensure the engine is in a known-good state before modification.

### Actions

1. Confirm current `main` (or working) branch runs without errors.
2. Confirm both strategies load and register correctly.
3. Do **not** deploy bots during this phase.

### Exit Criteria

* Engine boots cleanly
* Strategies import without warnings
* No runtime errors

---

## PHASE 1 — STRATEGY PARAMETER REPAIR

### Objective

Replace all overfit or inconsistent strategy numbers with **production-viable parameters**.

---

### STRATEGY A

## Jupiter Mean Reversion (US Session)

#### Replace ALL existing values with the following:

| Parameter           | Value                       |
| ------------------- | --------------------------- |
| Entry RSI           | ≤ 31 (single tick)          |
| Position Size       | $10                         |
| Take Profit         | +0.45%                      |
| Stop Loss           | -0.60%                      |
| Max Hold            | 25 minutes (hard exit)      |
| Early Exit          | RSI ≥ 48 → exit immediately |
| Confirmation        | NONE                        |
| Cooldown After Exit | 5 minutes                   |

#### Required Code Changes

* Remove any multi-bar confirmation logic
* Remove time-window PnL logic
* Ensure TP/SL are percentage-based
* Ensure time exit is unconditional at 25 minutes

---

### STRATEGY B

## RSI Bands (Conservative Scalper)

#### Replace ALL existing values with the following:

| Parameter            | Value                       |
| -------------------- | --------------------------- |
| Entry RSI            | ≤ 31 (single tick)          |
| Position Size        | $10                         |
| Phase 1 TP (0–5 min) | +0.35%                      |
| Phase 2 Hold         | 5–15 minutes                |
| Hard Stop            | -0.85% (always active)      |
| Forced Exit          | 15 minutes                  |
| RSI Exit             | RSI ≥ 52 → exit immediately |

#### Required Code Changes

* Implement two-phase TP logic using elapsed time
* Remove any percentage-of-notional math inconsistencies
* Remove any unlimited hold logic
* Ensure forced exit always triggers at 15 minutes

---

### Exit Criteria (Phase 1)

* Both strategies compile
* Parameters exactly match above tables
* No unused constants remain in strategy files

---

## PHASE 2 — JUNK REMOVAL (MANDATORY)

### Objective

Reduce cognitive and operational surface area.

### DELETE OR DISABLE:

* Any unused strategies
* Experimental indicators
* Legacy strategy configs
* Commented-out logic blocks
* Feature flags not referenced in active code
* Alternate entry thresholds not used

### RULE

If a line of code does not directly support:

* Strategy A
* Strategy B
* Execution
* Oracle
* Risk management

It is removed.

### Exit Criteria

* Only two strategies remain
* No dead code paths
* Repo size visibly reduced

---

## PHASE 3 — STRATEGY ISOLATION TEST

### Objective

Ensure each strategy works **independently**.

### Actions

1. Run engine with **only Strategy A enabled**
2. Confirm:

   * Entry on RSI ≤ 31
   * TP / SL / time exits fire correctly
3. Repeat with **only Strategy B enabled**

### Exit Criteria

* Each strategy can run alone without error
* Logs clearly show why trades exit

---

## PHASE 4 — DUAL STRATEGY COEXISTENCE

### Objective

Confirm both strategies can coexist without interference.

### Actions

* Enable both strategies
* Confirm:

  * Position limits respected
  * No double-entry collisions
  * Independent cooldowns respected

### Exit Criteria

* Engine stable with both strategies active
* No race conditions
* No unexpected pauses

---

## PHASE 5 — DEPLOYMENT READINESS CHECK

### Objective

Freeze V1.

### Checklist

* [ ] Exactly two strategies
* [ ] Parameters match agent.md
* [ ] $10 notional everywhere
* [ ] No TODOs
* [ ] No experimental logic
* [ ] No commented-out code
* [ ] Engine pauses correctly on bad data

### Rule

When this checklist is complete:
**STOP BUILDING. RUN THE SYSTEM.**

---

## AGENT TERMINATION CONDITION

This agent is **complete** when:

* The system trades with these parameters
* No further tuning is attempted without live data
* V1 is considered frozen

All future changes require a **new agent.md**.

---

## FINAL NOTE (FOR YOU, NOT THE AGENT)

This agent is intentionally boring.

Boring systems survive.
Surviving systems compound.

You are now in **operator mode**, not builder mode.
