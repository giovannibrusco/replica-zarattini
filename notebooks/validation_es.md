# Validazione replica su ES (dati IB, contratto continuo costruito da spec)

Dati: 9 contratti trimestrali ES da IB Gateway, stitching con **roll al
volume crossover** e **back-adjustment additivo** (`src/download_ib.py`).
Campione: **2024-05-30 → 2026-07-10** (530 giorni RTH, 205.530 barre).

Riproduzione: i numeri di questo report escono da `run_backtest` su
`data/es_1min.parquet` con `CostModel.es_futures()`, `unit_multiplier=50`,
`initial_equity=1M` (granularita': ~300k$ di notional per contratto).

## Sanity check

- 523/530 giorni con 390 barre piene; 7 mezze sedute note (3 lug, post
  Thanksgiving, vigilia: 225 barre = chiusura futures 13:15) ✓
- 0 duplicati, 0 prezzi non positivi, 236 barre a volume zero su 205k ✓
- 8 roll, tutti il lunedì della settimana di scadenza (dove avviene il
  crossover su ES), offset +50/+75 punti ≈ carry teorico a tassi 4-5% ✓
- Unico spike >2%: 2025-04-09 13:19 (annuncio pausa dazi) — coincide al
  minuto con il dataset SPY/Alpaca: i due dataset si cross-validano ✓

## Replica ES (slippage 0.25 tick, commissioni $0.85 + fees $1.40)

| | ES base | ES final | ES buy&hold |
|---|---|---|---|
| Sharpe | **0.52** | **-0.07** | 0.93 |
| CAGR | +7.8% | -2.1% | +14.0% |
| Max DD | -16.3% | -22.7% | -18.5% |
| Alfa ann. (t-stat) | +10.0% (0.8) | +1.3% (0.1) | — |
| Trades | 326 | 477 | — |
| Win rate | 53.4% | 37.7% | — |
| Payoff | 0.96 | 1.60 | — |

## Sensitivity slippage (final)

| Slippage | CAGR | Sharpe | Expectancy |
|---|---|---|---|
| 0.25 tick | -2.1% | -0.07 | -0.61 bps |
| 0.5 tick | -2.6% | -0.11 | -0.80 bps |
| 1.0 tick | -4.8% | -0.27 | -1.18 bps |

I costi non sono la causa del risultato negativo (~0.4 bps/round trip a
0.25 tick): è il segnale che nel periodo non paga.

## Il confronto decisivo: ES vs SPY, stesso periodo (2024-07-01 →)

| | Sharpe | CAGR | Trades | Win rate | Exp (bps) |
|---|---|---|---|---|---|
| ES base | 0.69 | +11.1% | 322 | 53.7% | +2.61 |
| SPY base | 0.67 | +10.9% | 320 | 55.6% | +3.21 |
| ES final | -0.04 | -1.7% | 473 | 37.8% | -0.60 |
| SPY final | 0.06 | -0.2% | 487 | 38.8% | -0.42 |

**Correlazione dei rendimenti giornalieri ES-final vs SPY-final: 0.97.**

## Conclusioni

1. **La domanda aperta è chiusa: il 2025-26 negativo NON era un artefatto
   del feed IEX.** Con dati CME completi (VWAP e volumi veri) la strategia
   produce risultati quasi identici (corr 0.97, stessi trade: 473 vs 487).
   La compressione dell'edge nel periodo recente è reale.
2. **La pipeline è cross-validata**: due fonti dati indipendenti (IB
   futures con stitching nostro; Alpaca azionario) producono lo stesso
   risultato — anche lo stitching è quindi implicitamente verificato.
3. **Nel regime recente la gerarchia del paper si inverte**: la exit base
   (trailing largo) batte la final (trailing stretto su VWAP/banda). Il
   trailing stretto viene "shakerato" dai rientri intraday nella Noise
   Area che poi ripartono. Con 2 anni di dati non è una conclusione
   statistica, ma è coerente su entrambi gli strumenti.
4. L'expectancy della base (+2.6 bps su ES) è nell'ordine della replica
   Quantitativo (+2 bps), pur su un periodo diverso.

## Caveat

- Campione corto (25 mesi): niente confronto con i regimi 2008/2020, e le
  differenze base/final non sono statisticamente conclusive.
- Vincolo IB: contratti scaduti disponibili solo ~2 anni; per lo storico
  lungo (2010+) resta necessario Databento (o equivalente).
- Equity 1M per la granularita' dei contratti ES; con MES la granularita'
  migliora di 10x a parita' di logica.
