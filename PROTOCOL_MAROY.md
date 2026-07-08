# Protocollo ex-ante — Esplorazione varianti "alla Maróy" con disciplina out-of-sample

**Congelato il 2026-07-08, PRIMA di eseguire qualsiasi backtest delle varianti.**
Questo documento definisce in modo chiuso e non modificabile l'esperimento.
Qualsiasi deviazione va dichiarata come tale nel report finale.

## Obiettivo

Verificare se, nello spazio di varianti esplorato da Maróy (2025), esiste una
configurazione che batta la strategia del paper (Zarattini 2024) **out-of-sample**,
correggendo per il bias di selezione. NON è un'ottimizzazione per produzione:
è un esperimento pilota su SPY/IEX; qualsiasi esito positivo richiede conferma
sulla fase ES prima di qualunque uso.

## Dataset e split

- Dati: SPY 1-min, Alpaca IEX, RTH — `data/spy_1min.parquet` (2020-07-27 → 2026-07-08)
- **In-sample (IS): dall'inizio del campione al 2023-12-31** — unico periodo
  usato per selezionare la variante vincente
- **Out-of-sample (OOS): dal 2024-01-01 alla fine del campione** — valutato
  UNA SOLA VOLTA, solo per la variante vincente IS e per il controllo
- Warmup indicatori: le barre precedenti all'inizio di ciascun periodo possono
  alimentare gli indicatori (sigma_t, vol daily), mai generare trade conteggiati

## Lista chiusa delle varianti (27 = 3 × 3 × 3)

| Dimensione | Valori | Note |
|---|---|---|
| Exit | `base` (banda opposta), `final` (max/min VWAP-banda; paper), `vwap` (solo VWAP; Maróy) | ladder escluso: non definito con precisione replicabile |
| Lookback Noise Area | 7, 14, 28 giorni | 14 = paper |
| Intervallo check | 15, 30, 60 minuti | 30 = paper; check da 10:00, ultimo ≤ 15:45 |

- **Controllo**: `final` / 14 giorni / 30 minuti (= replica del paper)
- Fissi per tutte le varianti: vol target 2%, cap leva 4×, vol lookback 14g
  (lo Sharpe è invariante alla scala di rischio: ottimizzarla è solo rumore),
  costi IB $0.0035/share min $0.35, slippage 0, chiusura forzata EOD, flip attivo.

## Regola di selezione (meccanica, nessuna discrezionalità)

1. Eseguire le 27 varianti SOLO su IS
2. Vincente = massimo **Sharpe annualizzato netto** su IS. Pareggi: variante
   più vicina al paper (nell'ordine: exit final, lookback 14, intervallo 30)
3. Pubblicare la tabella completa delle 27 (nessun risultato nascosto)

## Correzione per selezione multipla

**Deflated Sharpe Ratio** (Bailey & López de Prado 2014) del vincente IS:
- N = 27 trial; soglia dall'expected max SR sotto H0, con varianza degli SR
  stimata dai 27 trial; aggiustamento per skew/curtosi dei rendimenti
- Soglia dichiarata ex-ante: **DSR ≥ 0.95**

## Valutazione OOS (una sola volta)

Solo vincente IS + controllo. Criteri di successo, tutti e tre necessari:

- **C1**: DSR(IS) del vincente ≥ 0.95
- **C2**: Sharpe netto OOS del vincente > Sharpe netto OOS del controllo
- **C3**: Sharpe netto OOS del vincente > 0

Esiti: 3/3 → variante "promossa" (in attesa di conferma su ES). Altrimenti →
resta la configurazione del paper; l'esperimento si chiude e NON si riapre
con nuove varianti su questi stessi dati.

## Disclosure obbligatorie

1. **Il periodo OOS non è vergine**: la replica (config = controllo) è già
   stata eseguita sull'intero campione e sappiamo che il controllo perde nel
   2025-26. La selezione resta meccanica su IS, ma la lista delle varianti è
   stata definita dallo spazio del paper di Maróy, non progettata dopo aver
   visto l'OOS. Questo caveat non è eliminabile ed è il motivo per cui l'esito
   vale come pilota, non come scoperta.
2. Feed IEX: VWAP approssimato — tocca soprattutto le exit `final` e `vwap`.
3. Campione corto (IS ~3.4 anni, OOS ~2.5 anni): potenza statistica limitata.
