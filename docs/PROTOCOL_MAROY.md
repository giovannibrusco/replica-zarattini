# Ex-ante protocol — "Maróy-style" variant exploration with out-of-sample discipline

**Frozen on 2026-07-08, BEFORE running any backtest of the variants.**
This document defines the experiment in a closed and non-modifiable way.
Any deviation must be declared as such in the final report.

## Objective

To verify whether, within the variant space explored by Maróy (2025), there
exists a configuration that beats the paper's strategy (Zarattini 2024)
**out-of-sample**, after correcting for selection bias. This is NOT an
optimisation for production: it is a pilot experiment on SPY/IEX; any
positive outcome requires confirmation on the ES phase before any use.

## Dataset and split

- Data: SPY 1-min, Alpaca IEX, RTH — `data/spy_1min.parquet` (2020-07-27 → 2026-07-08)
- **In-sample (IS): from the start of the sample to 2023-12-31** — the only
  period used to select the winning variant
- **Out-of-sample (OOS): from 2024-01-01 to the end of the sample** —
  evaluated ONCE ONLY, and only for the IS winner and the control
- Indicator warmup: bars preceding the start of each period may feed the
  indicators (sigma_t, daily vol), but never generate counted trades

## Closed list of variants (27 = 3 × 3 × 3)

| Dimension | Values | Notes |
|---|---|---|
| Exit | `base` (opposite band), `final` (max/min VWAP-band; paper), `vwap` (VWAP only; Maróy) | ladder excluded: not defined precisely enough to replicate |
| Noise Area lookback | 7, 14, 28 days | 14 = paper |
| Check interval | 15, 30, 60 minutes | 30 = paper; checks from 10:00, last one ≤ 15:45 |

- **Control**: `final` / 14 days / 30 minutes (= the paper's replication)
- Fixed across all variants: vol target 2%, leverage cap 4×, vol lookback 14d
  (the Sharpe ratio is invariant to risk scale: optimising it is pure noise),
  IB costs $0.0035/share min $0.35, slippage 0, forced EOD close, flips on.

## Selection rule (mechanical, no discretion)

1. Run the 27 variants on IS ONLY
2. Winner = maximum **net annualised Sharpe** on IS. Ties: the variant
   closest to the paper (in order: exit final, lookback 14, interval 30)
3. Publish the complete table of all 27 (no hidden results)

## Correction for multiple selection

**Deflated Sharpe Ratio** (Bailey & López de Prado 2014) of the IS winner:
- N = 27 trials; threshold from the expected max SR under H0, with the
  variance of the SRs estimated from the 27 trials; adjustment for the
  skewness/kurtosis of the returns
- Threshold declared ex-ante: **DSR ≥ 0.95**

## OOS evaluation (once only)

IS winner + control only. Success criteria, all three required:

- **C1**: DSR(IS) of the winner ≥ 0.95
- **C2**: net OOS Sharpe of the winner > net OOS Sharpe of the control
- **C3**: net OOS Sharpe of the winner > 0

Outcomes: 3/3 → variant "promoted" (pending confirmation on ES). Otherwise →
the paper's configuration stands; the experiment closes and is NOT reopened
with new variants on this same data.

## Mandatory disclosures

1. **The OOS period is not virgin**: the replication (config = control) has
   already been run on the whole sample and we know the control loses in
   2025-26. Selection remains mechanical on IS, but the list of variants was
   defined from the variant space of Maróy's paper, not designed after seeing
   the OOS. This caveat cannot be eliminated and is the reason the outcome
   counts as a pilot, not as a discovery.
2. IEX feed: approximated VWAP — this affects mainly the `final` and `vwap`
   exits.
3. Short sample (IS ~3.4 years, OOS ~2.5 years): limited statistical power.

---

*Faithful English translation of the original Italian document. The frozen
version is commit `4d0a7cc` (2026-07-08), which predates every result
reported in `reports/maroy_experiment.md`; the translation itself changed no
content. The Italian original is retrievable from the git history.*
