# Esperimento Maróy — risultati (protocollo commit 4a98efe)

Eseguito una sola volta il 2026-07-08. Selezione meccanica, nessuna variante aggiunta dopo il congelamento.

## Griglia in-sample completa (2020-10-01 → 2023-12-31)

| exit   |   lookback |   interval |   sharpe_ann | cagr   | max_dd   |   n_trades | win_rate   |   expectancy_bps |
|:-------|-----------:|-----------:|-------------:|:-------|:---------|-----------:|:-----------|-----------------:|
| final  |         14 |         30 |         1.73 | +25.0% | -7.1%    |        746 | 42.8%      |             4.36 |
| vwap   |         14 |         60 |         1.68 | +24.5% | -8.2%    |        510 | 48.4%      |             6.17 |
| vwap   |         14 |         30 |         1.67 | +25.9% | -9.2%    |        636 | 46.4%      |             5    |
| vwap   |          7 |         60 |         1.66 | +24.2% | -9.5%    |        543 | 47.1%      |             6.31 |
| final  |         14 |         60 |         1.58 | +21.5% | -6.3%    |        549 | 48.5%      |             4.88 |
| vwap   |         14 |         15 |         1.51 | +24.2% | -7.3%    |        798 | 43.5%      |             3.75 |
| final  |          7 |         60 |         1.48 | +19.7% | -10.4%   |        590 | 47.1%      |             4.72 |
| final  |          7 |         30 |         1.45 | +20.5% | -11.5%   |        797 | 43.5%      |             3.35 |
| final  |         14 |         15 |         1.44 | +21.1% | -8.8%    |       1042 | 36.9%      |             2.67 |
| final  |          7 |         15 |         1.43 | +20.7% | -9.8%    |       1113 | 38.2%      |             2.38 |
| vwap   |         28 |         60 |         1.42 | +20.0% | -8.2%    |        486 | 48.6%      |             6.15 |
| final  |         28 |         60 |         1.3  | +17.2% | -9.6%    |        529 | 45.0%      |             4.68 |
| final  |         28 |         30 |         1.22 | +16.7% | -10.3%   |        710 | 40.4%      |             3.3  |
| vwap   |         28 |         30 |         1.21 | +18.0% | -9.6%    |        614 | 46.7%      |             3.95 |
| vwap   |          7 |         15 |         1.15 | +18.1% | -7.9%    |        849 | 41.5%      |             2.69 |
| base   |         14 |         30 |         1.12 | +20.8% | -14.6%   |        520 | 58.7%      |             5.02 |
| vwap   |          7 |         30 |         1.09 | +16.4% | -13.1%   |        686 | 44.3%      |             3.11 |
| final  |         28 |         15 |         1.08 | +14.9% | -10.9%   |       1002 | 36.0%      |             2.21 |
| vwap   |         28 |         15 |         1.01 | +15.3% | -9.9%    |        777 | 43.4%      |             2.66 |
| base   |         14 |         15 |         0.99 | +18.9% | -19.7%   |        572 | 57.9%      |             3.99 |
| base   |         14 |         60 |         0.96 | +16.2% | -23.3%   |        465 | 58.7%      |             4.4  |
| base   |          7 |         60 |         0.86 | +14.5% | -19.8%   |        490 | 57.6%      |             5.02 |
| base   |         28 |         30 |         0.85 | +15.0% | -22.6%   |        499 | 59.5%      |             4.44 |
| base   |          7 |         30 |         0.76 | +13.5% | -17.7%   |        557 | 56.7%      |             4.03 |
| base   |         28 |         15 |         0.72 | +12.9% | -26.6%   |        549 | 58.7%      |             3.35 |
| base   |         28 |         60 |         0.61 | +9.6%  | -29.5%   |        443 | 59.1%      |             4.12 |
| base   |          7 |         15 |         0.52 | +8.7%  | -28.3%   |        606 | 55.0%      |             2.16 |

## Vincente IS: `final` / lookback 14g / check 30min

- Sharpe IS: **1.73** (controllo IS: 1.73)
- **Deflated Sharpe Ratio: 0.972** (N=27 trial; expected max SR sotto H0: 0.71 annualizzato)
- C1 (DSR ≥ 0.95): **PASS**

## Out-of-sample (2024-01-01 → fine campione) — valutato una sola volta

|                  | Vincente   | Controllo (paper)   |
|:-----------------|:-----------|:--------------------|
| Sharpe           | 0.16       | 0.16                |
| CAGR             | +1.3%      | +1.3%               |
| Max DD           | -24.2%     | -24.2%              |
| Trades           | 603        | 603                 |
| Win rate         | 38.5%      | 38.5%               |
| Expectancy (bps) | -0.17      | -0.17               |

- C2 (Sharpe OOS vincente > controllo): **FAIL**
- C3 (Sharpe OOS vincente > 0): **PASS**

## Verdetto

**Criteri non superati: resta la configurazione del paper.** Come da protocollo, l'esperimento e' chiuso e non si riapre con nuove varianti su questi stessi dati.

Disclosure: vedi PROTOCOL_MAROY.md (OOS non vergine, feed IEX, campione corto).
