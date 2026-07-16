# Validazione replica — SPY (dati Alpaca IEX)

Campione: **2020-07-27 → 2026-07-08** (1493 giorni, 569,591 barre 1-min RTH).

## Base vs Final vs benchmark passivo

|                   | base    | final   | SPY buy&hold   |
|:------------------|:--------|:--------|:---------------|
| Total return      | +132.7% | +139.6% | +130.5%        |
| CAGR              | +15.32% | +15.89% | +15.14%        |
| Vol ann.          | 18.5%   | 14.3%   | 16.7%          |
| Sharpe            | 0.86    | 1.11    | 0.93           |
| Max DD            | -23.6%  | -24.2%  | -25.4%         |
| Alfa ann.         | +16.5%  | +16.7%  | —              |
| t-stat alfa       | 2.18    | 2.85    | —              |
| Beta              | -0.04   | -0.06   | —              |
| Trades            | 941     | 1379    | —              |
| Win rate          | 57.0%   | 41.0%   | —              |
| Payoff            | 0.88    | 1.69    | —              |
| Expectancy (bps)  | +4.09   | +2.58   | —              |
| Max losing streak | 7       | 10      | —              |

Benchmark esterni attesi: paper (SPY 2007-24) Sharpe ~1.33, alfa ~19.6%, beta ~0; replica Quantitativo (ES) ~+2 bps/trade, win rate ~36%, payoff ~2.1.

## Robustezza temporale (variante final)

|      | Strategia   |   Sharpe | Alfa ann.   | SPY B&H   |
|-----:|:------------|---------:|:------------|:----------|
| 2020 | +9.2%       |     1.45 | +26.3%      | +15.6%    |
| 2021 | +30.6%      |     2.03 | +26.9%      | +27.0%    |
| 2022 | +25.8%      |     1.7  | +23.1%      | -19.5%    |
| 2023 | +29.3%      |     2    | +25.8%      | +24.3%    |
| 2024 | +24.8%      |     1.51 | +28.0%      | +23.3%    |
| 2025 | -4.9%       |    -0.27 | -3.1%       | +16.3%    |
| 2026 | -12.9%      |    -1.91 | -25.1%      | +9.3%     |

## Regimi VIX (variante final)

|       | Total return   |   Sharpe |   Giorni |
|:------|:---------------|---------:|---------:|
| <15   | +34.6%         |     2.37 |      262 |
| 15-20 | +16.6%         |     0.5  |      636 |
| 20-30 | +48.1%         |     1.35 |      515 |
| 30-40 | -0.3%          |    -0.01 |       74 |
| >40   | +3.4%          |     9.14 |        5 |

## Sensitivity slippage (variante final)

|              | CAGR   |   Sharpe |   Expectancy (bps) | Win rate   |
|:-------------|:-------|---------:|-------------------:|:-----------|
| $0.000/share | +15.9% |     1.11 |               2.58 | 41.0%      |
| $0.005/share | +14.5% |     1.02 |               2.37 | 40.5%      |
| $0.010/share | +13.2% |     0.94 |               2.16 | 40.0%      |

## Caveat

- **Feed IEX** (~3% del volume): VWAP approssimato (tocca la exit final) e minuti mancanti sparsi (il motore usa l'ultimo prezzo disponibile al check).
- **Campione dal 2020-07** (limite free tier Alpaca): niente 2008 ne' periodo pre-COVID; il confronto col paper (2007-24) e' quindi di ordine di grandezza.
- Commissioni IB $0.0035/share (min $0.35) come nel paper; slippage base 0.
- Nei bucket VIX>30 il campione e' esiguo: nessuna conclusione.
