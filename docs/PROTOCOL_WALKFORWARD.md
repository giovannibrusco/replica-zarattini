# Addendum ex-ante — Walk-forward sulla lista chiusa di varianti

**Congelato il 2026-07-08, PRIMA di eseguire il walk-forward.**
Estende PROTOCOL_MAROY.md (commit 4a98efe). Non aggiunge varianti: cambia
solo la procedura di selezione, da statica (un solo split) ad adattiva.

## Rapporto con l'esperimento precedente

L'esperimento a split singolo è chiuso (esito: resta la config del paper).
Il walk-forward risponde a una domanda diversa: *"riselezionare
periodicamente la variante in base al passato recente avrebbe aggiunto
valore rispetto a tenere fissa la config del paper?"* La selezione a ogni
punto usa SOLO dati precedenti a quel punto: nessun look-ahead. Il residuo
di contaminazione (conosciamo già i risultati full-sample del controllo e
la griglia IS) è dichiarato: l'esito vale come pilota, come tutto il resto
su questi dati.

## Design (UNICO — vietato provarne altri su questi dati)

- **Universo**: le stesse 27 varianti della lista chiusa (3 exit × 3
  lookback × 3 intervalli), stessi costi, stesso vol targeting
- **Finestra di selezione**: 252 giorni di trading trailing
- **Frequenza di riselezione**: trimestrale (1 gen / 1 apr / 1 lug / 1 ott)
- **Metrica di selezione**: Sharpe annualizzato netto sulla finestra
  trailing; tie-break = vicinanza alla config del paper (come nel
  protocollo base); minimo 200 osservazioni valide nella finestra
- **Primo punto di selezione**: 2021-10-01 (primo trimestre con 252 giorni
  di storia valutabile dopo il warmup del 2020-10-01)
- **Meccanica**: la variante selezionata si applica per tutto il trimestre
  successivo; lo switch avviene overnight (le strategie sono flat a fine
  giornata, quindi il cambio è implementabile senza costi aggiuntivi)
- **Ricostruzione**: si concatenano i rendimenti giornalieri netti della
  variante attiva in ciascun trimestre (equivalente a un conto unico che
  cambia regole overnight, essendo i rendimenti invarianti di scala)

## Criterio di successo (ex-ante)

Periodo di valutazione: 2021-10-01 → fine campione, identico per tutti.

- **W1**: Sharpe netto del walk-forward > Sharpe netto del controllo
  (config paper fissa) sullo stesso periodo

Esito binario su W1. Si riportano inoltre (descrittivi, non decisionali):
CAGR, max drawdown, sequenza delle varianti selezionate e numero di switch,
Sharpe del walk-forward vs controllo anno per anno.

Se W1 fallisce: l'adattivita' non aggiunge valore su questi dati e il tema
si chiude fino alla fase ES. Nessuna variazione di finestra, frequenza o
metrica verra' provata su questo campione.
