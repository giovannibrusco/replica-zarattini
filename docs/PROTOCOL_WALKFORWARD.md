# Ex-ante addendum — Walk-forward on the closed list of variants

**Frozen on 2026-07-08, BEFORE running the walk-forward.**
Extends PROTOCOL_MAROY.md (commit 4d0a7cc). It adds no variants: it changes
only the selection procedure, from static (a single split) to adaptive.

## Relationship with the previous experiment

The single-split experiment is closed (outcome: the paper's config stands).
The walk-forward answers a different question: *"would periodically
reselecting the variant on the basis of the recent past have added value
relative to keeping the paper's config fixed?"* Selection at each point uses
ONLY data preceding that point: no look-ahead. The residual contamination (we
already know the control's full-sample results and the IS grid) is declared:
the outcome counts as a pilot, like everything else on this data.

## Design (SINGLE — trying others on this data is forbidden)

- **Universe**: the same 27 variants of the closed list (3 exits × 3
  lookbacks × 3 intervals), same costs, same vol targeting
- **Selection window**: 252 trailing trading days
- **Reselection frequency**: quarterly (1 Jan / 1 Apr / 1 Jul / 1 Oct)
- **Selection metric**: net annualised Sharpe over the trailing window;
  tie-break = closeness to the paper's config (as in the base protocol);
  minimum 200 valid observations in the window
- **First selection point**: 2021-10-01 (the first quarter with 252 days of
  evaluable history after the 2020-10-01 warmup)
- **Mechanics**: the selected variant applies for the whole following
  quarter; the switch happens overnight (the strategies are flat at the end
  of the day, so the change is implementable at no additional cost)
- **Reconstruction**: the net daily returns of the variant active in each
  quarter are concatenated (equivalent to a single account that changes rules
  overnight, returns being scale-invariant)

## Success criterion (ex-ante)

Evaluation period: 2021-10-01 → end of sample, identical for all.

- **W1**: net Sharpe of the walk-forward > net Sharpe of the control
  (paper's fixed config) over the same period

Binary outcome on W1. The following are also reported (descriptive, not
decisional): CAGR, max drawdown, the sequence of selected variants and the
number of switches, walk-forward vs control Sharpe year by year.

If W1 fails: adaptivity adds no value on this data and the topic closes until
the ES phase. No variation of window, frequency or metric will be tried on
this sample.

---

*Faithful English translation of the original Italian document. The frozen
version is commit `dbf73fb` (2026-07-08), which predates every result
reported in `reports/walkforward_experiment.md`; the translation itself
changed no content. The Italian original is retrievable from the git history.*
