# Replication validation on ES (IB data, continuous contract built per spec)

Data: 9 quarterly ES contracts from IB Gateway, stitched with a **volume-crossover
roll** and **additive back-adjustment** (`src/download_ib.py`).
Sample: **2024-05-30 → 2026-07-10** (530 RTH days, 205,530 bars).

Reproduction: the numbers in this report come from `run_backtest` on
`data/es_1min.parquet` with `CostModel.es_futures()`, `unit_multiplier=50`,
`initial_equity=1M` (granularity: ~$300k of notional per contract).

## Sanity check

- 523/530 days with a full 390 bars; 7 known half sessions (3 Jul, day after
  Thanksgiving, Christmas Eve: 225 bars = 13:15 futures close) ✓
- 0 duplicates, 0 non-positive prices, 236 zero-volume bars out of 205k ✓
- 8 rolls, all on the Monday of expiry week (where the crossover happens on
  ES), offsets +50/+75 points ≈ theoretical carry at 4-5% rates ✓
- Only spike >2%: 2025-04-09 13:19 (tariff-pause announcement) — matches the
  SPY/Alpaca dataset to the minute: the two datasets cross-validate ✓

## ES replication (slippage 0.25 tick, commissions $0.85 + fees $1.40)

| | ES base | ES final | ES buy&hold |
|---|---|---|---|
| Sharpe | **0.52** | **-0.07** | 0.93 |
| CAGR | +7.8% | -2.1% | +14.0% |
| Max DD | -16.3% | -22.7% | -18.5% |
| Ann. alpha (t-stat) | +10.0% (0.8) | +1.3% (0.1) | — |
| Trades | 326 | 477 | — |
| Win rate | 53.4% | 37.7% | — |
| Payoff | 0.96 | 1.60 | — |

## Slippage sensitivity (final)

| Slippage | CAGR | Sharpe | Expectancy |
|---|---|---|---|
| 0.25 tick | -2.1% | -0.07 | -0.61 bps |
| 0.5 tick | -2.6% | -0.11 | -0.80 bps |
| 1.0 tick | -4.8% | -0.27 | -1.18 bps |

Costs are not the cause of the negative result (~0.4 bps/round trip at
0.25 tick): it is the signal that does not pay in this period.

## The decisive comparison: ES vs SPY, same period (2024-07-01 →)

| | Sharpe | CAGR | Trades | Win rate | Exp (bps) |
|---|---|---|---|---|---|
| ES base | 0.69 | +11.1% | 322 | 53.7% | +2.61 |
| SPY base | 0.67 | +10.9% | 320 | 55.6% | +3.21 |
| ES final | -0.04 | -1.7% | 473 | 37.8% | -0.60 |
| SPY final | 0.06 | -0.2% | 487 | 38.8% | -0.42 |

**Correlation of daily returns, ES-final vs SPY-final: 0.97.**

## Conclusions

1. **The open question is settled: the negative 2025-26 was NOT an artefact
   of the IEX feed.** With complete CME data (real VWAP and volumes) the
   strategy produces almost identical results (corr 0.97, same trades: 473 vs
   487). The recent compression of the edge is real.
2. **The pipeline is cross-validated**: two independent data sources (IB
   futures with our own stitching; Alpaca equities) produce the same result —
   so the stitching is implicitly verified too.
3. **In the recent regime the paper's hierarchy inverts**: the base exit
   (wide trailing stop) beats final (tight trailing on VWAP/band). The tight
   stop gets shaken out by intraday re-entries into the Noise Area that then
   resume. With 2 years of data this is not a statistical conclusion, but it
   is consistent across both instruments.
4. The base variant's expectancy (+2.6 bps on ES) is in line with the
   Quantitativo replication (+2 bps), albeit over a different period.

## Caveats

- Short sample (25 months): no comparison with the 2008/2020 regimes, and the
  base/final differences are not statistically conclusive.
- IB constraint: expired contracts are only available for ~2 years; for the
  long history (2010+) Databento (or equivalent) is still required.
- 1M equity because of ES contract granularity; with MES the granularity
  improves 10x for identical logic.
