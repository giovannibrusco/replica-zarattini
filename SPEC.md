# SPEC — Replica "Beat the Market" (Zarattini, Aziz, Barbon 2024) su ES/MES

## Contesto e obiettivo

Stiamo costruendo una strategia di trading algoritmico partendo dalla replica di un paper pubblicato, per avere un benchmark esterno contro cui validare il codice. Il paper scelto è:

> Zarattini, C., Aziz, A., Barbon, A. (2024). *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)*. SSRN 4824172, Swiss Finance Institute.

Risultati dichiarati dal paper (su SPY, mag 2007 – inizio 2024, netto di commissioni IB $0.0035/share): **total return 1.985%, rendimento annualizzato 19,6%, Sharpe 1,33, alfa annualizzato ~19,6% statisticamente significativo vs SPY**.

Noi replichiamo su **futures ES o MES** (dati Interactive Brokers, barre 1 minuto). Esiste una replica pubblica su ES (Quantitativo, gen 2025) che trova: ~+2bps/trade, win rate ~36%, payoff ratio ~2,09 — utile come secondo benchmark.

Obiettivo finale (fase successiva, NON in questo blocco): valutare la strategia sotto i vincoli Apex Trader Funding (trailing drawdown, consistency rule) via Monte Carlo.

## Logica della strategia

Momentum intraday condizionato: si definisce una "Noise Area" attorno all'open basata sul movimento tipico degli ultimi 14 giorni a ogni orario della sessione. Prezzo dentro le bande = rumore, nessun trade. Breakout delle bande = squilibrio domanda/offerta anomalo → trend-following nella direzione della rottura, con trailing stop dinamici.

## Regole esatte

### 1. Noise Area
Per ogni minuto-della-sessione t (RTH 09:30–16:00 ET):

```
sigma_t = media su d ∈ ultimi 14 giorni di trading di |P_{d,t} / O_d − 1|
```

dove `P_{d,t}` = prezzo al minuto t del giorno d, `O_d` = open RTH del giorno d.

Bande del giorno corrente D (gestione gap tramite ancoraggio a open E close precedente):

```
UpperBound_t = max(O_D, C_{D−1}) × (1 + sigma_t)
LowerBound_t = min(O_D, C_{D−1}) × (1 − sigma_t)
```

⚠️ L'ancoraggio a max/min(Open, Close precedente) è essenziale: in presenza di gap overnight l'area si allarga. Molte repliche sbagliano questo dettaglio.

### 2. Entry (solo a intervalli di 30 minuti)
Check ai timestamp HH:00 e HH:30 (10:00, 10:30, …, 15:30):
- Prezzo > UpperBound_t → **LONG**
- Prezzo < LowerBound_t → **SHORT**
- Flip consentito (da long a short e viceversa se il segnale opposto scatta)
- Nessun nuovo entry che non possa essere chiuso entro le 16:00

### 3. Exit — due varianti da implementare entrambe
- **Base**: trailing stop = banda opposta (per un long: esci se prezzo < LowerBound_t)
- **Finale (quella del paper con i risultati migliori)**: per un long, esci se prezzo scende sotto max(VWAP_t, UpperBound_t) — cioè se rientra nella Noise Area o attraversa il VWAP di giornata. Speculare per gli short.
- VWAP = VWAP di sessione RTH, calcolato da 09:30
- Check exit agli stessi intervalli di 30 minuti
- **Chiusura forzata di tutte le posizioni alle 16:00 ET** (zero overnight)

### 4. Sizing
Volatility targeting al 2% giornaliero:

```
contratti = floor( (Equity × 0.02 / sigma_daily_14d) / notional_per_contratto )
```

con `sigma_daily_14d` = vol giornaliera realizzata a 14 giorni, e **cap di leva a 4×** (come nel paper e nella replica Quantitativo).

### 5. Costi (futures, per transazione — moltiplicare ×2 per round trip)
- Commissione: $0.85/contratto (ES; scalare per MES)
- Exchange + regulatory fees: $1.40/contratto
- Slippage: 0.25 tick per transazione (0.5 tick per round trip)
- Sensitivity analysis obbligatoria: rieseguire con slippage 0.5 e 1 tick per transazione

## Parametri CONGELATI — vietato ottimizzare

| Parametro | Valore | Fonte |
|---|---|---|
| Lookback Noise Area | 14 giorni | paper |
| Intervallo esecuzione | 30 minuti | paper |
| Vol target giornaliera | 2% | paper |
| Cap leva | 4× | paper |
| Lookback vol per sizing | 14 giorni | paper |

Motivo: il follow-up di Maróy (2025) mostra Sharpe >3 ottimizzando questi parametri in-sample — classico data mining bias. Qualsiasi variante (es. exit alternative su VWAP puro o ladder) va definita ex-ante e testata SOLO out-of-sample con parametri congelati. Nessuna selezione a posteriori del vincitore in-sample.

## Dati

- Fonte: Interactive Brokers via API (ib_insync o ib_async)
- Strumento: ES (o MES), barre 1 minuto, RTH per il segnale
- Serve il contratto continuo: stitching sui roll (roll al volume crossover o N giorni prima di scadenza — documentare la regola scelta), back-adjustment additivo
- Scaricare il massimo storico disponibile; salvare in parquet locale prima di qualsiasi backtest
- Attenzione ai limiti di pacing IB sulle richieste storiche (batch con pause)

## Piano di validazione

1. **Sanity check dati**: continuità del contratto continuo, nessun buco nei minuti RTH, volumi plausibili
2. **Replica base vs finale**: confrontare le due varianti di exit; la finale deve dominare la base come nel paper (Tabelle 1–2)
3. **Benchmark esterni**: ordine di grandezza coerente con paper (Sharpe ~1,3 su SPY) e replica Quantitativo su ES (+2bps/trade, WR ~36%, payoff ~2,1)
4. **Robustezza temporale**: risultati per anno; test escludendo il 2008 (anno anomalo che gonfia i risultati se incluso); performance per regime VIX (il paper trova Sharpe crescente con la vol, ~3,5 con VIX>40)
5. **Sensitivity sui costi**: slippage 0.25 / 0.5 / 1 tick
6. **Statistiche trade-level**: win rate, payoff ratio, expectancy, distribuzione perdite singole, losing streak massima (serve per la fase Apex)

## Struttura progetto proposta

```
zarattini_replica/
├── data/                    # parquet contratto continuo
├── src/
│   ├── download_ib.py       # download + stitching + storage
│   ├── noise_area.py        # sigma_t, bande, VWAP
│   ├── backtest.py          # engine event-driven, entry/exit/flip, costi
│   ├── sizing.py            # vol targeting + cap leva
│   └── stats.py             # metriche, tabelle per anno/regime
├── notebooks/
│   └── validation.ipynb     # confronto con benchmark, sensitivity
└── README.md
```

## Ordine di lavoro

1. `download_ib.py` — scaricare e validare i dati (blocco a sé, verificare qualità prima di procedere)
2. `noise_area.py` con test unitari sul calcolo di sigma_t e sulla gestione gap
3. `backtest.py` variante base → variante finale
4. `stats.py` + notebook di validazione contro i benchmark
5. STOP e review dei risultati prima di qualsiasi estensione

## Fuori scope (fasi successive, non toccare ora)

- Calibrazione Apex (trailing drawdown, consistency rule, Monte Carlo pass probability)
- Exit alternative (Maróy) in protocollo out-of-sample
- Overnight drift (Boyarchenko/Larsen/Whelan) come strategia #2
- Portafoglio multi-strategia
