# Replica "Beat the Market" (Zarattini, Aziz, Barbon 2024)

Replica della strategia di momentum intraday con Noise Area del paper
*Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)*
(SSRN 4824172), come benchmark esterno per validare il codice.

**Fase corrente: replica su SPY con dati Alpaca** (barre 1 minuto, feed IEX
gratuito) per il confronto diretto con i risultati del paper. La migrazione a
ES/MES (dati futures) è prevista come fase successiva: il motore è già
parametrico su moltiplicatore e modello di costi futures.

## Struttura

```
├── data/                    # parquet barre 1-min (non versionato)
├── src/
│   ├── download_alpaca.py   # download barre 1-min da Alpaca -> parquet
│   ├── validate_data.py     # sanity check dati (punto 1 del piano)
│   ├── noise_area.py        # sigma_t, bande con ancoraggio gap, VWAP
│   ├── backtest.py          # engine event-driven, entry/exit/flip, costi
│   ├── sizing.py            # vol targeting 2% + cap leva 4x
│   └── stats.py             # metriche, tabelle per anno/regime VIX
├── tests/                   # test unitari + integrazione su dati sintetici
└── notebooks/               # validazione contro i benchmark
```

## Uso

```bash
pip install -r requirements.txt
python -m pytest tests/            # 33 test su dati sintetici

# download dati (servono le chiavi Alpaca, account paper gratuito)
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...
python -m src.download_alpaca --symbol SPY --start 2016-01-01
python -m src.validate_data data/spy_1min.parquet
```

Backtest:

```python
import pandas as pd
from src.backtest import run_backtest, CostModel
from src.stats import performance_summary, trade_stats, yearly_table

bars = pd.read_parquet("data/spy_1min.parquet")
res = run_backtest(bars, exit_mode="final")   # oppure "base"
print(performance_summary(res.daily_returns))
print(trade_stats(res.trades))
```

## Regole implementate (vedi spec)

- **Noise Area**: `sigma_t` = media a 14 giorni di `|P_{d,t}/O_d − 1|`
  (giorno corrente escluso); bande ancorate a `max/min(Open, Close prec.)`
  per la gestione dei gap overnight.
- **Entry/exit solo ai check di 30 minuti** (10:00 … 15:30), flip consentito,
  chiusura forzata a fine sessione (zero overnight).
- **Exit "base"**: banda opposta. **Exit "final"** (paper): per un long,
  uscita sotto `max(VWAP, UpperBound)`; speculare per gli short.
- **Sizing**: vol targeting 2% giornaliero, vol realizzata a 14 giorni,
  cap di leva 4×.
- **Costi** parametrici: azioni ($0.0035/share IB, min $0.35) o futures
  (commissioni+fees per contratto, slippage in tick: `CostModel.es_futures()`).

**Parametri congelati** (lookback 14g, check 30min, vol target 2%, leva 4×):
non vanno ottimizzati — vedi spec sul data mining bias (Maróy 2025).

## Note sui dati

Il feed IEX gratuito di Alpaca copre ~3% del volume consolidato: prezzi
affidabili per SPY ma VWAP approssimato (rilevante per la exit "final").
Il confronto con il paper va letto con questo caveat; la replica su ES con
dati CME completi è il passo successivo.
