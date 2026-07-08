"""Download barre 1-minuto ES/MES da Interactive Brokers (TWS o IB Gateway).

Uso (sulla macchina dove gira IB Gateway, gia' loggato e con API abilitata):

    pip install ib_async pandas pyarrow
    python -m src.download_ib --port 4001 --out data/es_1min.parquet

    # Gateway live: porta 4001 | Gateway paper: 4002
    # TWS live: 7496 | TWS paper: 7497

Caratteristiche:
- contratto continuo IB (CONTFUT): storico lungo, oltre il limite dei ~2
  anni che IB impone sui contratti scaduti
- scarica all'indietro dal presente fino a --start (o al primo dato
  disponibile), a blocchi di --duration (default "2 D", prudente)
- checkpoint su parquet ogni --checkpoint-every blocchi: se il processo si
  interrompe, RILANCIARE LO STESSO COMANDO riprende da dove era
- al riavvio fa anche il "top-up" in avanti (dall'ultimo dato salvato a ora)
- rispetta il pacing IB (pausa tra richieste, backoff sulle violazioni)

⚠️ Deviazione documentata dalla spec: il roll del CONTFUT e' quello di IB
(switch del front alla scadenza), non il volume-crossover, e NON c'e'
back-adjustment. La strategia e' flat overnight quindi i salti di roll non
toccano il PnL dei trade; toccano solo prev_close (ancoraggio bande) e la
vol daily nei ~4 giorni di roll l'anno. Da flaggare nella validazione.

Requisiti lato IB:
- API abilitata: Configure -> Settings -> API -> "Enable ActiveX and Socket
  Clients" (lasciare "Read-Only API" ATTIVO: per lo storico basta e non
  permette ordini)
- sottoscrizione dati CME (es. "CME Real-Time (NP,L1)", pochi $/mese
  non-professional): senza, IB rifiuta lo storico dei futures (errore 162)
"""

from __future__ import annotations

import argparse
import os
import sys
import time as _time
from datetime import datetime, timedelta, timezone

import pandas as pd

ET = "America/New_York"
PAUSE_S = 2.0          # pausa tra richieste (pacing IB)
PACING_WAIT_S = 65.0   # attesa dopo una pacing violation


def _connect(host: str, port: int, client_id: int):
    try:
        from ib_async import IB
    except ImportError:
        sys.exit("Manca ib_async: pip install ib_async")
    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=20)
    return ib


def _qualify(ib, symbol: str, exchange: str):
    from ib_async import ContFuture

    contracts = ib.qualifyContracts(ContFuture(symbol, exchange, "USD"))
    if not contracts:
        sys.exit(f"Contratto continuo {symbol}@{exchange} non risolto")
    c = contracts[0]
    print(f"Contratto: {c.localSymbol or c.symbol} conId={c.conId} ({exchange})")
    return c


def _fetch_chunk(ib, contract, end_dt: datetime, duration: str) -> pd.DataFrame:
    """Un blocco di barre 1-min RTH che termina a end_dt (UTC). Gestisce
    retry su pacing violation."""
    from ib_async import util

    for attempt in range(5):
        try:
            bars = ib.reqHistoricalData(
                contract,
                endDateTime=end_dt,
                durationStr=duration,
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=2,  # timestamp UTC
            )
            df = util.df(bars)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.set_index("date")[["open", "high", "low", "close", "volume"]]
            df.index = pd.DatetimeIndex(df.index).tz_convert(ET)
            return df
        except Exception as exc:
            msg = str(exc).lower()
            if "pacing" in msg or "violation" in msg:
                print(f"  pacing violation, attendo {PACING_WAIT_S:.0f}s...")
                _time.sleep(PACING_WAIT_S)
            elif attempt < 4:
                print(f"  errore ({exc}), retry {attempt + 1}...")
                _time.sleep(5 * (attempt + 1))
            else:
                raise
    return pd.DataFrame()


def _save(df: pd.DataFrame, path: str) -> None:
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df.to_parquet(path)


def download(
    host: str,
    port: int,
    client_id: int,
    symbol: str,
    exchange: str,
    start: datetime | None,
    duration: str,
    out: str,
    checkpoint_every: int,
) -> None:
    ib = _connect(host, port, client_id)
    contract = _qualify(ib, symbol, exchange)

    head = ib.reqHeadTimeStamp(contract, whatToShow="TRADES", useRTH=True)
    head = pd.Timestamp(head).tz_convert("UTC") if pd.Timestamp(head).tzinfo else pd.Timestamp(head, tz="UTC")
    print(f"Primo dato disponibile su IB: {head}")
    floor_dt = max(head, pd.Timestamp(start, tz="UTC")) if start else head
    print(f"Scarico fino a: {floor_dt}")

    existing = pd.read_parquet(out) if os.path.exists(out) else pd.DataFrame()
    if not existing.empty:
        print(f"Riprendo da checkpoint: {len(existing):,} barre "
              f"[{existing.index[0]} -> {existing.index[-1]}]")

    frames = [existing] if not existing.empty else []
    n_chunks = 0

    def _run_leg(end_dt: pd.Timestamp, stop_at: pd.Timestamp, label: str):
        """Scarica all'indietro da end_dt fino a stop_at."""
        nonlocal n_chunks, frames
        empty_streak = 0
        while end_dt > stop_at:
            chunk = _fetch_chunk(ib, contract, end_dt.to_pydatetime(), duration)
            if chunk.empty:
                empty_streak += 1
                if empty_streak >= 5:
                    print(f"  {label}: 5 blocchi vuoti consecutivi, stop")
                    break
                end_dt -= timedelta(days=4)  # salta weekend/festivita'
                continue
            empty_streak = 0
            frames.append(chunk)
            earliest = chunk.index[0].tz_convert("UTC")
            print(f"  {label} {earliest.date()}: +{len(chunk)} barre")
            if earliest >= end_dt:  # nessun progresso: forza lo step
                end_dt -= timedelta(days=2)
            else:
                end_dt = earliest
            n_chunks += 1
            if n_chunks % checkpoint_every == 0:
                _save(pd.concat(frames), out)
                print(f"  checkpoint: salvate {sum(len(f) for f in frames):,} barre")
            _time.sleep(PAUSE_S)

    now = pd.Timestamp.now(tz="UTC")
    if not existing.empty:
        # top-up in avanti: dal dato piu' recente salvato a ora
        latest = existing.index[-1].tz_convert("UTC")
        if now - latest > pd.Timedelta(hours=1):
            _run_leg(now, latest, "top-up")
        # backfill: dal dato piu' vecchio salvato all'inizio richiesto
        _run_leg(existing.index[0].tz_convert("UTC"), floor_dt, "backfill")
    else:
        _run_leg(now, floor_dt, "download")

    final = pd.concat(frames) if frames else pd.DataFrame()
    if final.empty:
        sys.exit("Nessun dato scaricato.")
    _save(final, out)
    final = pd.read_parquet(out)
    print(f"\nFATTO: {len(final):,} barre in {out}")
    print(f"Range: {final.index[0]} -> {final.index[-1]}")
    ib.disconnect()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4001,
                   help="4001 gw live, 4002 gw paper, 7496 TWS live, 7497 TWS paper")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--symbol", default="ES", help="ES o MES")
    p.add_argument("--exchange", default="CME")
    p.add_argument("--start", default=None,
                   help="YYYY-MM-DD; default: tutto lo storico disponibile")
    p.add_argument("--duration", default="2 D",
                   help='blocco per richiesta (es. "2 D", "1 W"); 2 D e\' prudente')
    p.add_argument("--out", default=None)
    p.add_argument("--checkpoint-every", type=int, default=25)
    args = p.parse_args()

    start = (
        datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        if args.start else None
    )
    out = args.out or f"data/{args.symbol.lower()}_1min.parquet"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    download(
        args.host, args.port, args.client_id, args.symbol, args.exchange,
        start, args.duration, out, args.checkpoint_every,
    )


if __name__ == "__main__":
    main()
