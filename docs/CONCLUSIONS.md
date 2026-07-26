# Conclusions — "Beat the Market" replication (Zarattini 2024)

*Close of the replication and analysis phase, 2026-07. Data: SPY/Alpaca
2020-07 → 2026-07 (6 years) and ES/IB 2024-05 → 2026-07 (25 months).*

## What we established

### 1. The code replicates the paper — primary objective achieved

On SPY 2020-26 with the paper's costs: Sharpe 1.11, annualised alpha
+16.7% (t 2.85), beta -0.06; the final exit dominates base over the long
sample; win rate 41% / payoff 1.69 / +2.6 bps per trade, consistent with
the paper (Sharpe 1.33 over 2007-24) and with the Quantitativo replication
on ES. Strong cross-validation: the same strategy on two independent data
sources (ES futures from IB with our own stitching; SPY from Alpaca)
produces daily returns correlated at 0.97.

### 2. The edge existed and was robust through 2024

2020-2024: per-year Sharpe between 1.4 and 2.0, alpha 23-28%/year. 2022 is
the strategy's signature: +25.8% with SPY at -19.5%, zero beta, a "long
volatility" profile. It was not an artefact: it survives costs
(sensitivity up to 1 tick of slippage) and the change of data source.

### 3. Since 2025 the edge has compressed — and that is a fact, not an artefact

- SPY final 2025: -4.9% (Sharpe -0.27); 2026 YTD: -12.9% (Sharpe -1.91)
- ES final over the same period: almost identical (corr 0.97) → rules out
  feed problems (IEX VWAP) and stitching problems
- Costs ruled out (~0.4 bps/round trip vs -0.6 bps/trade of expectancy)

### 4. It is not a parameter problem — optimisation saves nothing

- Disciplined "Maroy" grid (27 variants, DSR, OOS): the in-sample winner IS
  the paper's configuration. No variant promoted.
- Walk-forward (quarterly reselection): DESTROYS value (Sharpe 0.57 vs
  0.92 for the fixed control). The 1-year ranking among correlated
  variants is noise.
- In 2024-26 the base exit beats final on both instruments (Sharpe ~0.7 vs
  ~0): an interesting observation but POST-HOC — using it now would be
  exactly the a-posteriori selection the protocols forbid.

### 5. The remaining limit to what we can know

We do not know whether 18 lean months are within the strategy's historical
norm: the paper (2007-24) shows multi-year weak stretches (2012-2015)
followed by recovery. Distinguishing a "regime pause" from an "edge
arbitraged away" requires the 2007-2019 history (Databento) or time.

## Summary judgement on the strategy

A REAL strategy in the sample studied, with a valuable profile (beta 0,
pays in crises), but with an edge currently compressed to zero or below.
It is NOT allocable today as a standalone strategy on the basis of this
data; nor can it be written off as "dead" — the recent sample is short and
the historical profile admits long pauses.

## Recommended next steps (in order)

1. **NO to the Apex phase for now.** With a recent Sharpe of ~0, any Monte
   Carlo on trailing drawdown and the consistency rule would reject the
   strategy (or worse: it would pass by luck on simulations calibrated on
   the good past). The Apex phase only makes sense if and when the edge
   reappears.
2. **Frozen forward monitoring (recommended).** The paper's config
   (final/14/30) + base as a reference, with rules and re-evaluation
   criteria written ex-ante (e.g. review at 6 months or on a new vol
   regime). It turns the question "pause or death?" into data that matures
   on its own, at zero cost. The IB data updates by re-running download_ib.
3. **Strategy #2 from the spec (overnight drift)** as a parallel research
   track with the same discipline (spec → protocol → replication →
   validation). It diversifies research risk instead of continuing to dig
   in a space that has already said no.
4. **(Optional) Long history via Databento** if the card issue is resolved:
   2007-2019 would say whether the current lean stretch has precedents. It
   is the only data purchase that would genuinely change the conclusions.

## What NOT to do

- Optimise further on these samples (Maroy and the walk-forward have
  already paid that price for us).
- Promote the base exit because it "has been doing better lately" without a
  new out-of-sample protocol and forward time.
- Take the strategy to capital (own or funded) on the basis of the
  2020-24 period alone.
