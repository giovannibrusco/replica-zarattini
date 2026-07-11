"""Download barre 1-minuto ES/MES da IB: singoli contratti trimestrali +
stitching con roll al volume crossover + back-adjustment additivo (spec).

Perche' non il contratto continuo di IB: (a) errore 10339 — IB non permette
piu' endDateTime sui CONTFUT, quindi niente paginazione all'indietro;
(b) il CONTFUT non e' back-adjusted. I singoli contratti invece sono
scaricabili fino a ~2 anni dopo la scadenza (limite IB): si ottengono
quindi ~2 anni di continuo costruito secondo la spec.

Uso (sulla macchina dove gira IB Gateway loggato, API abilitata):

    pip install ib_async pandas pyarrow
    python -m src.download_ib --port 4001     # 4002 se Gateway paper

Output:
    data/es_1min.parquet   contratto continuo back-adjusted, RTH, tz ET
    data/es_rolls.csv      tabella dei roll (data, contratti, offset)
    data/ib_raw/*.parquet  dati grezzi per contratto (riusati al riavvio)

Riprendibile: i contratti gia' scaricati non vengono richiesti di nuovo;
lo stitching viene ricalcolato a ogni esecuzione dai file grezzi.

Regola di roll (documentata, da spec): roll alla prima sessione RTH in cui
il volume del contratto successivo supera quello del front (volume
crossover); fallback = ultima sessione prima della scadenza. Il front vale
fino alla sessione di roll inclusa, il successivo dalla sessione dopo.
Back-adjustment additivo: offset = close(next) - close(front) alla
sessione di roll, applicato cumulativamente all'indietro.
"""

from __future__ import annotations

import argparse
import os
import sys
import time as _time
from datetime import timedelta

import pandas as pd

ET = "America/New_York"
PAUSE_S = 2.0
PACING_WAIT_S = 65.0
OVERLAP_DAYS = 15          # finestra prima della scadenza del front
EXPIRED_LIMIT_DAYS = 700   # limite IB ~2 anni sui contratti scaduti
RTH_START, RTH_LAST = "09:30", "15:59"


def _connect(host: str, port: int, client_id: int):
    try:
        from ib_async import IB
    except ImportError:
        sys.exit("Manca ib_async: pip install ib_async")
    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=20)
    return ib


def quarterly_expiries(now: pd.Timestamp) -> list[str]:
    """YYYYMM dei contratti trimestrali: dal piu' vecchio scaricabile
    (~2 anni fa) al front attuale (+1 di margine)."""
    months = []
    start = now - pd.Timedelta(days=EXPIRED_LIMIT_DAYS)
    y = start.year
    while y <= now.year + 1:
        for m in (3, 6, 9, 12):
            ts = pd.Timestamp(year=y, month=m, day=20, tz="UTC")
            if start <= ts <= now + pd.Timedelta(days=120):
                months.append(f"{y}{m:02d}")
        y += 1
    return months


def _qualify_contracts(ib, symbol: str, exchange: str, months: list[str]):
    from ib_async import Contract

    out = []
    for ym in months:
        c = Contract(
            secType="FUT", symbol=symbol, exchange=exchange, currency="USD",
            lastTradeDateOrContractMonth=ym, includeExpired=True,
        )
        got = ib.qualifyContracts(c)
        if got:
            q = got[0]
            expiry = pd.Timestamp(q.lastTradeDateOrContractMonth, tz="UTC")
            out.append((expiry, q))
            print(f"  {q.localSymbol}: scadenza {expiry.date()}")
        else:
            print(f"  {symbol} {ym}: non risolto (troppo vecchio?), salto")
    out.sort(key=lambda t: t[0])
    return out


def _fetch_range(ib, contract, start: pd.Timestamp, end: pd.Timestamp,
                 duration: str, label: str) -> pd.DataFrame:
    """Barre 1-min RTH [start, end] paginando all'indietro da end."""
    from ib_async import util

    frames = []
    end_dt = end
    empty_streak = 0
    while end_dt > start:
        for attempt in range(5):
            try:
                bars = ib.reqHistoricalData(
                    contract, endDateTime=end_dt.to_pydatetime(),
                    durationStr=duration, barSizeSetting="1 min",
                    whatToShow="TRADES", useRTH=True, formatDate=2,
                )
                break
            except Exception as exc:
                msg = str(exc).lower()
                if "pacing" in msg or "violation" in msg:
                    print(f"    pacing violation, attendo {PACING_WAIT_S:.0f}s")
                    _time.sleep(PACING_WAIT_S)
                elif attempt < 4:
                    _time.sleep(5 * (attempt + 1))
                else:
                    raise
        df = util.df(bars)
        if df is None or df.empty:
            empty_streak += 1
            if empty_streak >= 4:
                break
            end_dt -= timedelta(days=4)
            continue
        empty_streak = 0
        chunk = df.set_index("date")[["open", "high", "low", "close", "volume"]]
        chunk.index = pd.DatetimeIndex(chunk.index).tz_convert(ET)
        frames.append(chunk)
        earliest = chunk.index[0].tz_convert("UTC")
        print(f"    {label} {earliest.date()}: +{len(chunk)}")
        end_dt = earliest if earliest < end_dt else end_dt - timedelta(days=2)
        _time.sleep(PAUSE_S)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames)
    return out[~out.index.duplicated(keep="first")].sort_index()


def download_contract(ib, contract, expiry, prev_expiry, raw_dir: str,
                      duration: str, now: pd.Timestamp) -> pd.DataFrame:
    """Scarica (o riusa) le barre del contratto nella sua finestra da front."""
    sym = contract.localSymbol
    path = os.path.join(raw_dir, f"{sym}.parquet")
    win_start = prev_expiry - pd.Timedelta(days=OVERLAP_DAYS)
    win_end = min(expiry, now)

    existing = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()
    if not existing.empty:
        have_end = existing.index[-1].tz_convert("UTC")
        if have_end >= win_end - pd.Timedelta(days=3):
            print(f"  {sym}: gia' completo ({len(existing):,} barre), riuso")
            return existing
        print(f"  {sym}: top-up da {have_end.date()}")
        add = _fetch_range(ib, contract, have_end, win_end, duration, sym)
        existing = pd.concat([existing, add])
        existing = existing[~existing.index.duplicated(keep="first")].sort_index()
        existing.to_parquet(path)
        return existing

    print(f"  {sym}: scarico [{win_start.date()} -> {win_end.date()}]")
    df = _fetch_range(ib, contract, win_start, win_end, duration, sym)
    if not df.empty:
        df.to_parquet(path)
    return df


def stitch(per_contract: list[tuple[str, pd.Timestamp, pd.DataFrame]]):
    """Continuo back-adjusted da contratti ordinati per scadenza.

    Ritorna (continuo, tabella roll). Volume crossover su volumi RTH."""
    def rth(df):
        return df.between_time(RTH_START, RTH_LAST)

    def daily_close(df):
        r = rth(df)
        return r["close"].groupby(r.index.normalize()).last()

    def daily_vol(df):
        r = rth(df)
        return r["volume"].groupby(r.index.normalize()).sum()

    rolls = []
    segments = []
    seg_start = None  # inizio (esclusivo) del segmento del contratto corrente

    for i, (sym, expiry, df) in enumerate(per_contract):
        if i + 1 < len(per_contract):
            nxt_sym, nxt_expiry, nxt_df = per_contract[i + 1]
            va, vb = daily_vol(df), daily_vol(nxt_df)
            common = va.index.intersection(vb.index)
            cross = [d for d in common if vb[d] > va[d]]
            if cross:
                roll_day = cross[0]
            else:
                sessions = va.index[va.index < expiry.tz_convert(ET).normalize()]
                roll_day = sessions[-1]
                print(f"  ATTENZIONE {sym}: nessun crossover, roll forzato {roll_day.date()}")
            ca, cb = daily_close(df), daily_close(nxt_df)
            offset = float(cb[roll_day] - ca[roll_day])
            rolls.append({"roll_day": roll_day.date(), "from": sym,
                          "to": nxt_sym, "offset": offset})
        else:
            roll_day = None

        seg = df if seg_start is None else df[df.index.normalize() > seg_start]
        if roll_day is not None:
            seg = seg[seg.index.normalize() <= roll_day]
        segments.append(seg)
        seg_start = roll_day

    # back-adjustment additivo cumulativo (l'ultimo segmento resta invariato)
    adjusted = []
    n = len(segments)
    for i, seg in enumerate(segments):
        offset = sum(r["offset"] for r in rolls[i:]) if i < n - 1 else 0.0
        s = seg.copy()
        for col in ("open", "high", "low", "close"):
            s[col] = s[col] + offset
        adjusted.append(s)

    cont = pd.concat(adjusted)
    cont = cont[~cont.index.duplicated(keep="first")].sort_index()
    return cont, pd.DataFrame(rolls)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4001,
                   help="4001 gw live, 4002 gw paper, 7496/7497 TWS")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--symbol", default="ES", help="ES o MES")
    p.add_argument("--exchange", default="CME")
    p.add_argument("--duration", default="2 D")
    p.add_argument("--out", default=None)
    p.add_argument("--raw-dir", default="data/ib_raw")
    args = p.parse_args()

    out = args.out or f"data/{args.symbol.lower()}_1min.parquet"
    os.makedirs(args.raw_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    now = pd.Timestamp.now(tz="UTC")
    ib = _connect(args.host, args.port, args.client_id)

    print("Risolvo i contratti trimestrali:")
    contracts = _qualify_contracts(
        ib, args.symbol, args.exchange, quarterly_expiries(now)
    )
    if len(contracts) < 2:
        sys.exit("Servono almeno 2 contratti risolti per lo stitching.")

    per_contract = []
    prev_expiry = contracts[0][0] - pd.Timedelta(days=95)  # finestra del piu' vecchio
    for expiry, c in contracts:
        if expiry - now > pd.Timedelta(days=100):
            continue  # contratti lontani: non ancora front, inutili
        df = download_contract(ib, c, expiry, prev_expiry, args.raw_dir,
                               args.duration, now)
        if not df.empty:
            per_contract.append((c.localSymbol, expiry, df))
        else:
            print(f"  {c.localSymbol}: nessun dato (oltre il limite dei 2 anni?)")
        prev_expiry = expiry

    if len(per_contract) < 2:
        sys.exit("Dati insufficienti per lo stitching.")

    print("\nStitching (roll al volume crossover, back-adjust additivo):")
    cont, rolls = stitch(per_contract)
    print(rolls.to_string(index=False))
    rolls.to_csv(out.replace(".parquet", "_rolls.csv"), index=False)
    cont.to_parquet(out)
    print(f"\nFATTO: {len(cont):,} barre in {out}")
    print(f"Range: {cont.index[0]} -> {cont.index[-1]}")
    ib.disconnect()


if __name__ == "__main__":
    main()
