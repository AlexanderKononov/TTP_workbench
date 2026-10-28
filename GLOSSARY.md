# Crypto Trading System

The language of a human-confirmed trading system that finds repeating price spikes in low-liquidity crypto markets and trades them with small sums, built by the Owner together with role-based Claude agents.

> Terms marked *(provisional)* came from the initial brief and are not yet sharpened.

## Language

### People & agents

**Owner**:
The only human in the system: sets budgets and limits, approves plans, and confirms cases.
_Avoid_: User, trader

**Governor**:
The main interactive Claude session: plans with the Owner, dispatches work to roles, and is the only agent that asks the Owner for decisions.
_Avoid_: Orchestrator, lead agent, manager

**Role**:
A named Claude agent with one area of expertise, its own access and its own memory. Every role works in the same repo, on the same code and strategies.
_Avoid_: Bot, worker

**Dev role**:
A role whose expertise is building, testing and validating the trading system's code, data and infrastructure.

**Trading role**:
A role whose expertise is trading itself: helps the Owner design strategies, risk management and sizing, and plans and controls what the dev roles build.

### Market

**Venue** *(provisional)*:
An exchange or broker where crypto can be traded, centralised or decentralised.
_Avoid_: Broker (when meaning any venue), platform

**Market** *(provisional)*:
A single tradable pair on a venue, e.g. `XYZ/USDT` on a specific exchange.
_Avoid_: Ticker, symbol (when meaning pair + venue)

**Low-liquidity market** *(provisional)*:
A market whose depth, volume or spread falls within the thresholds that define the system's target universe.
_Avoid_: Illiquid, small cap

**Spike pattern** *(provisional)*:
A robot-like price spike in a low-liquidity market that repeats regularly for some period of time.

### Trading system

**Trading system**:
The deterministic software this repo builds: screens markets, evaluates candidates, executes confirmed cases and reports results. No LLM runs inside it.
_Avoid_: Bot, AI trader

**Execution service**:
The part of the trading system that holds venue credentials and places orders, only when strategy signals, a confirmation and its limits all allow it.
_Avoid_: Executor agent, broker

**Screen** *(provisional)*:
A run that scans venues and markets and produces candidates.
_Avoid_: Scan, search

**Candidate** *(provisional)*:
A market the screen flags as worth evaluating with a strategy.
_Avoid_: Potential coin, signal

**Strategy**:
A rule set, written as code, defining when to enter, size and exit a position in a market.
_Avoid_: Algo, bot

**Case**:
A proposal to run one strategy on a set of markets for a time window, with evidence, risks and a suggested budget and limits, presented to the Owner for confirmation.
_Avoid_: Proposal, recommendation, trade idea

**Confirmation**:
The Owner's explicit approval of a case, fixing its budget, limits and expiry. The only thing that authorises execution; within it the trading system trades on its own.
_Avoid_: Approval, sign-off

**Budget**:
The maximum capital the Owner allocates to one confirmed case.

**Limits**:
The risk constraints fixed by a confirmation (max loss, max position per market, max slippage, max open orders) that the execution service enforces; breaching one stops the case.
_Avoid_: Rules, settings

**Expiry**:
The end of a confirmed case's time window, after which it stops trading.

### Lifecycle

**Stage**:
Where a strategy is on its road to real money: backtest, paper, or live. Promotion between stages is an Owner decision.

**Paper trading**:
Running a strategy against live market data with simulated orders.
_Avoid_: Dry run, simulation (when meaning this stage)

**Gate**:
A point where work stops until the Owner decides.
_Avoid_: Checkpoint, approval step
