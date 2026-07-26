# Walk-forward experiment — results (protocol commit dbf73fb)

Period evaluated: 2021-10-01 → 2026-07-08 (1194 days). Quarterly selection on trailing 252-day Sharpe, universe = the 27 variants of the closed list.

## Comparison (same period)

|                        |   sharpe | cagr   | max_dd   |
|:-----------------------|---------:|:-------|:---------|
| Walk-forward           |     0.57 | +7.9%  | -27.6%   |
| Control (paper, fixed) |     0.92 | +12.7% | -24.2%   |

**W1 (WF Sharpe > control): FAIL**

## Variants selected per quarter

| quarter    | variant    |
|:-----------|:-----------|
| 2021-10-01 | vwap/14/60 |
| 2022-01-03 | vwap/14/60 |
| 2022-04-01 | vwap/14/30 |
| 2022-07-01 | vwap/14/30 |
| 2022-10-03 | vwap/7/60  |
| 2023-01-03 | vwap/28/60 |
| 2023-04-03 | vwap/28/60 |
| 2023-07-03 | final/7/60 |
| 2023-10-02 | final/7/60 |
| 2024-01-02 | final/7/30 |
| 2024-04-01 | base/14/15 |
| 2024-07-01 | final/7/30 |
| 2024-10-01 | final/7/30 |
| 2025-01-02 | vwap/7/30  |
| 2025-04-01 | final/7/60 |
| 2025-07-01 | vwap/28/60 |
| 2025-10-01 | base/7/60  |
| 2026-01-02 | base/14/60 |
| 2026-04-01 | base/7/30  |
| 2026-07-01 | base/14/15 |

Switches made: 14 out of 19 reselections.

## Per year (Sharpe)

|      |   Walk-forward |   Control |
|-----:|---------------:|----------:|
| 2021 |           0.73 |      2.46 |
| 2022 |           1.72 |      1.7  |
| 2023 |           1.76 |      2    |
| 2024 |           0.64 |      1.51 |
| 2025 |          -0.68 |     -0.27 |
| 2026 |          -1.2  |     -1.91 |

## Verdict

W1 failed: periodic reselection does not beat the paper's fixed configuration. Per the protocol the topic is closed until the ES phase; no other design will be tried on this data.
