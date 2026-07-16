# Conclusioni — Replica "Beat the Market" (Zarattini 2024)

*Chiusura della fase di replica e analisi, 2026-07. Dati: SPY/Alpaca
2020-07 → 2026-07 (6 anni) e ES/IB 2024-05 → 2026-07 (25 mesi).*

## Cosa abbiamo stabilito

### 1. Il codice replica il paper — obiettivo primario raggiunto

Su SPY 2020-26 con i costi del paper: Sharpe 1.11, alfa annualizzato
+16.7% (t 2.85), beta -0.06; la exit final domina la base sul campione
lungo; win rate 41% / payoff 1.69 / +2.6 bps per trade, coerenti con il
paper (Sharpe 1.33 su 2007-24) e con la replica Quantitativo su ES.
Cross-validazione forte: la stessa strategia su due fonti dati
indipendenti (ES futures IB con stitching nostro; SPY Alpaca) produce
rendimenti giornalieri correlati 0.97.

### 2. L'edge esisteva ed era robusto fino al 2024

2020-2024: Sharpe per anno tra 1.4 e 2.0, alfa 23-28%/anno. Il 2022 e' la
firma della strategia: +25.8% con SPY a -19.5%, beta zero, profilo "long
volatility". Non era un artefatto: sopravvive ai costi (sensitivity fino a
1 tick di slippage) e alla fonte dati.

### 3. Dal 2025 l'edge si e' compresso — ed e' un fatto, non un artefatto

- SPY final 2025: -4.9% (Sharpe -0.27); 2026 YTD: -12.9% (Sharpe -1.91)
- ES final sullo stesso periodo: quasi identico (corr 0.97) → esclusi
  problemi di feed (VWAP IEX) e di stitching
- Esclusi i costi (~0.4 bps/round trip vs -0.6 bps/trade di expectancy)

### 4. Non e' un problema di parametri — l'ottimizzazione non salva nulla

- Griglia "Maroy" disciplinata (27 varianti, DSR, OOS): il vincente
  in-sample E' la configurazione del paper. Nessuna variante promossa.
- Walk-forward (riselezione trimestrale): DISTRUGGE valore (Sharpe 0.57 vs
  0.92 del controllo fisso). La classifica a 1 anno tra varianti correlate
  e' rumore.
- Nel 2024-26 la exit base batte la final su entrambi gli strumenti
  (Sharpe ~0.7 vs ~0): osservazione interessante ma POST-HOC — usarla ora
  sarebbe la selezione a posteriori che i protocolli vietano.

### 5. Il limite conoscitivo residuo

Non sappiamo se 18 mesi di magra siano nella norma storica della
strategia: il paper (2007-24) mostra tratti pluriennali deboli
(2012-2015) seguiti da ripresa. Distinguere "pausa di regime" da "edge
arbitraggiato via" richiede lo storico 2007-2019 (Databento) o tempo.

## Giudizio sintetico sulla strategia

Strategia REALE nel campione studiato, con profilo prezioso (beta 0,
rende nelle crisi), ma con edge attualmente compresso a zero o sotto.
NON e' allocabile oggi come strategia standalone sulla base di questi
dati; non e' nemmeno liquidabile come "morta" — il campione recente e'
corto e il profilo storico ammette pause lunghe.

## Prossimi passi raccomandati (in ordine)

1. **NO alla fase Apex adesso.** Con Sharpe recente ~0, qualsiasi Monte
   Carlo su trailing drawdown e consistency rule boccerebbe la strategia
   (o peggio: passerebbe per fortuna su simulazioni calibrate sul passato
   buono). La fase Apex ha senso solo se/quando l'edge riappare.
2. **Forward monitoring congelato (raccomandato).** Config del paper
   (final/14/30) + base come riferimento, regole e criteri di
   rivalutazione scritti ex-ante (es. rivedere a 6 mesi o a nuovo regime
   di vol). Trasforma la domanda "pausa o morte?" in dati che maturano da
   soli, a costo zero. I dati IB si aggiornano rilanciando download_ib.
3. **Strategia #2 della spec (overnight drift)** come pista di ricerca
   parallela con la stessa disciplina (spec → protocollo → replica →
   validazione). Diversifica il rischio-ricerca invece di continuare a
   scavare in uno spazio che ha gia' detto no.
4. **(Opzionale) Storico lungo via Databento** se si sblocca la carta:
   2007-2019 direbbe se la magra attuale ha precedenti. E' l'unico
   acquisto di dati che cambierebbe davvero le conclusioni.

## Cosa NON fare

- Ottimizzare ancora su questi campioni (Maroy e walk-forward l'hanno
  gia' pagato per noi).
- Promuovere la exit base perche' "ultimamente va meglio" senza un
  protocollo out-of-sample nuovo e tempo forward.
- Portare la strategia su capitale (proprio o funded) sulla base del
  solo periodo 2020-24.
