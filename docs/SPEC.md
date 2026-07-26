# SPEC — "Beat the Market" replication (Zarattini, Aziz, Barbon 2024) on ES/MES

## Context and objective

We are building an algorithmic trading strategy starting from the replication
of a published paper, in order to have an external benchmark against which to
validate the code. The chosen paper is:

> Zarattini, C., Aziz, A., Barbon, A. (2024). *Beat the Market: An Effective
> Intraday Momentum Strategy for S&P500 ETF (SPY)*. SSRN 4824172, Swiss
> Finance Institute.

Results reported by the paper (on SPY, May 2007 – early 2024, net of IB
commissions of $0.0035/share): **total return 1,985%, annualised return
19.6%, Sharpe 1.33, annualised alpha ~19.6%, statistically significant vs
SPY**.

We replicate on **ES or MES futures** (Interactive Brokers data, 1-minute
bars). A public replication on ES exists (Quantitativo, Jan 2025) which finds:
~+2bps/trade, win rate ~36%, payoff ratio ~2.09 — useful as a second
benchmark.

Final objective (later phase, NOT in this block): evaluate the strategy under
Apex Trader Funding constraints (trailing drawdown, consistency rule) via
Monte Carlo.

## Strategy logic

Conditional intraday momentum: a "Noise Area" is defined around the open,
based on the typical movement of the last 14 days at each time of the
session. Price inside the bands = noise, no trade. A breakout of the bands =
an anomalous supply/demand imbalance → trend-following in the direction of
the break, with dynamic trailing stops.

## Exact rules

### 1. Noise Area
For each minute-of-session t (RTH 09:30–16:00 ET):

```
sigma_t = mean over d ∈ last 14 trading days of |P_{d,t} / O_d − 1|
```

where `P_{d,t}` = price at minute t of day d, `O_d` = RTH open of day d.

Bands for the current day D (gap handling via anchoring to both the open AND
the previous close):

```
UpperBound_t = max(O_D, C_{D−1}) × (1 + sigma_t)
LowerBound_t = min(O_D, C_{D−1}) × (1 − sigma_t)
```

⚠️ Anchoring to max/min(Open, previous Close) is essential: in the presence of
an overnight gap the area widens. Many replications get this detail wrong.

### 2. Entry (only at 30-minute intervals)
Checks at the HH:00 and HH:30 timestamps (10:00, 10:30, …, 15:30):
- Price > UpperBound_t → **LONG**
- Price < LowerBound_t → **SHORT**
- Flips allowed (long to short and vice versa if the opposite signal fires)
- No new entry that could not be closed by 16:00

### 3. Exit — two variants, both to be implemented
- **Base**: trailing stop = the opposite band (for a long: exit if price < LowerBound_t)
- **Final (the paper's variant, with the best results)**: for a long, exit if
  the price falls below max(VWAP_t, UpperBound_t) — i.e. if it re-enters the
  Noise Area or crosses the session VWAP. Mirror image for shorts.
- VWAP = RTH session VWAP, computed from 09:30
- Exit checks at the same 30-minute intervals
- **Forced close of all positions at 16:00 ET** (zero overnight)

### 4. Sizing
Volatility targeting at 2% daily:

```
contracts = floor( (Equity × 0.02 / sigma_daily_14d) / notional_per_contract )
```

with `sigma_daily_14d` = 14-day realised daily vol, and a **leverage cap of
4×** (as in the paper and in the Quantitativo replication).

### 5. Costs (futures, per transaction — multiply ×2 for a round trip)
- Commission: $0.85/contract (ES; scale for MES)
- Exchange + regulatory fees: $1.40/contract
- Slippage: 0.25 tick per transaction (0.5 tick per round trip)
- Mandatory sensitivity analysis: re-run with slippage of 0.5 and 1 tick per
  transaction

## FROZEN parameters — optimising is forbidden

| Parameter | Value | Source |
|---|---|---|
| Noise Area lookback | 14 days | paper |
| Execution interval | 30 minutes | paper |
| Daily vol target | 2% | paper |
| Leverage cap | 4× | paper |
| Vol lookback for sizing | 14 days | paper |

Reason: Maróy's (2025) follow-up shows Sharpe >3 by optimising these
parameters in-sample — classic data mining bias. Any variant (e.g. alternative
exits on pure VWAP or a ladder) must be defined ex-ante and tested ONLY
out-of-sample with frozen parameters. No a-posteriori selection of the
in-sample winner.

## Data

- Source: Interactive Brokers via API (ib_insync or ib_async)
- Instrument: ES (or MES), 1-minute bars, RTH for the signal
- A continuous contract is needed: stitching across rolls (roll at the volume
  crossover or N days before expiry — document the chosen rule), additive
  back-adjustment
- Download the maximum history available; save to a local parquet before any
  backtest
- Mind IB's pacing limits on historical requests (batch with pauses)

## Validation plan

1. **Data sanity check**: continuity of the continuous contract, no holes in
   the RTH minutes, plausible volumes
2. **Base vs final replication**: compare the two exit variants; final must
   dominate base as in the paper (Tables 1–2)
3. **External benchmarks**: order of magnitude consistent with the paper
   (Sharpe ~1.3 on SPY) and with the Quantitativo replication on ES
   (+2bps/trade, WR ~36%, payoff ~2.1)
4. **Temporal robustness**: results per year; a test excluding 2008 (an
   anomalous year that inflates the results if included); performance per VIX
   regime (the paper finds Sharpe increasing with vol, ~3.5 with VIX>40)
5. **Cost sensitivity**: slippage 0.25 / 0.5 / 1 tick
6. **Trade-level statistics**: win rate, payoff ratio, expectancy,
   distribution of individual losses, longest losing streak (needed for the
   Apex phase)

## Proposed project structure

```
zarattini_replica/
├── data/                    # continuous-contract parquet
├── src/
│   ├── download_ib.py       # download + stitching + storage
│   ├── noise_area.py        # sigma_t, bands, VWAP
│   ├── backtest.py          # event-driven engine, entry/exit/flip, costs
│   ├── sizing.py            # vol targeting + leverage cap
│   └── stats.py             # metrics, per-year/per-regime tables
├── notebooks/
│   └── validation.ipynb     # benchmark comparison, sensitivity
└── README.md
```

## Order of work

1. `download_ib.py` — download and validate the data (a block of its own,
   verify quality before proceeding)
2. `noise_area.py` with unit tests on the sigma_t computation and on gap
   handling
3. `backtest.py` base variant → final variant
4. `stats.py` + a validation notebook against the benchmarks
5. STOP and review the results before any extension

## Out of scope (later phases, do not touch now)

- Apex calibration (trailing drawdown, consistency rule, Monte Carlo pass
  probability)
- Alternative exits (Maróy) under an out-of-sample protocol
- Overnight drift (Boyarchenko/Larsen/Whelan) as strategy #2
- Multi-strategy portfolio

---

*Faithful English translation of the original Italian specification (the
project brief, frozen before implementation). The Italian original is
retrievable from the git history.*
