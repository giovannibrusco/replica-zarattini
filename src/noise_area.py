"""Noise Area, sigma_t, bande e VWAP di sessione.

Replica di Zarattini, Aziz, Barbon (2024) "Beat the Market".

Convenzioni sui dati in ingresso:
- DataFrame di barre a 1 minuto con indice DatetimeIndex tz-aware (America/New_York)
- colonne: open, high, low, close, volume
- solo sessione RTH: barre etichettate da 09:30 a 15:59 inclusa (la barra
  etichettata HH:MM copre [HH:MM, HH:MM+1))

Definizioni (spec):
    sigma_t   = media sugli ultimi `lookback` giorni di |P_{d,t} / O_d - 1|
                (il giorno corrente e' SEMPRE escluso)
    Upper_t   = max(O_D, C_{D-1}) * (1 + sigma_t)
    Lower_t   = min(O_D, C_{D-1}) * (1 - sigma_t)
    VWAP_t    = VWAP di sessione da 09:30, prezzo tipico (H+L+C)/3

L'ancoraggio a max/min(Open, Close precedente) gestisce i gap overnight:
con un gap la Noise Area si allarga fino a coprire entrambi i riferimenti.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RTH_START = "09:30"
RTH_LAST_BAR = "15:59"  # ultima barra a 1 minuto della sessione RTH

DEFAULT_LOOKBACK = 14  # giorni — parametro CONGELATO da spec, non ottimizzare


def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Mantiene solo le barre RTH (etichette 09:30..15:59)."""
    if df.index.tz is None:
        raise ValueError("l'indice deve essere tz-aware (America/New_York)")
    return df.between_time(RTH_START, RTH_LAST_BAR)


def _day_key(index: pd.DatetimeIndex) -> pd.Index:
    return index.normalize()


def session_opens(df: pd.DataFrame) -> pd.Series:
    """Open RTH di ogni giorno (open della prima barra della sessione)."""
    return df["open"].groupby(_day_key(df.index)).first()


def session_closes(df: pd.DataFrame) -> pd.Series:
    """Close RTH di ogni giorno (close dell'ultima barra della sessione)."""
    return df["close"].groupby(_day_key(df.index)).last()


def compute_sigma(
    df: pd.DataFrame,
    lookback: int = DEFAULT_LOOKBACK,
    min_obs: int | None = None,
) -> pd.Series:
    """sigma_t per ogni barra: media a `lookback` giorni di |P_{d,t}/O_d - 1|.

    Il giorno corrente e' escluso (shift di un giorno). Per gestire mezze
    sedute (early close) in cui alcuni minuti mancano, la media richiede
    almeno `min_obs` osservazioni disponibili nella finestra (default:
    lookback // 2); sotto quella soglia sigma_t e' NaN e il backtest non
    opera a quel minuto.
    """
    if min_obs is None:
        min_obs = max(1, lookback // 2)

    days = _day_key(df.index)
    opens = session_opens(df).reindex(days)
    opens.index = df.index
    move = (df["close"] / opens - 1.0).abs()

    # matrice giorni x minuto-della-sessione
    frame = pd.DataFrame(
        {"day": days, "tod": df.index.time, "move": move.to_numpy()}
    )
    pivot = frame.pivot(index="day", columns="tod", values="move")

    sigma_by_day = (
        pivot.rolling(lookback, min_periods=min_obs).mean().shift(1)
    )

    # riporta in forma lunga allineata alle barre originali
    long = sigma_by_day.stack(future_stack=True).rename("sigma")
    keys = pd.MultiIndex.from_arrays([days, df.index.time])
    out = pd.Series(long.reindex(keys).to_numpy(), index=df.index, name="sigma")
    return out


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP di sessione da 09:30, con prezzo tipico (H+L+C)/3."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    days = _day_key(df.index)
    pv = (tp * df["volume"]).groupby(days).cumsum()
    v = df["volume"].groupby(days).cumsum()
    vwap = pv / v
    vwap.name = "vwap"
    return vwap


def build_indicators(
    df: pd.DataFrame,
    lookback: int = DEFAULT_LOOKBACK,
    min_obs: int | None = None,
) -> pd.DataFrame:
    """DataFrame arricchito con sigma, bande, vwap, open di giornata e close precedente.

    Le righe dei primi `lookback` giorni hanno sigma/bande NaN (warmup).
    """
    df = filter_rth(df).sort_index()
    days = _day_key(df.index)

    opens = session_opens(df)
    closes = session_closes(df)
    prev_close = closes.shift(1)

    upper_anchor = np.maximum(opens, prev_close)
    lower_anchor = np.minimum(opens, prev_close)

    out = df.copy()
    out["day_open"] = opens.reindex(days).to_numpy()
    out["prev_close"] = prev_close.reindex(days).to_numpy()
    out["sigma"] = compute_sigma(df, lookback=lookback, min_obs=min_obs)
    out["upper"] = upper_anchor.reindex(days).to_numpy() * (1.0 + out["sigma"])
    out["lower"] = lower_anchor.reindex(days).to_numpy() * (1.0 - out["sigma"])
    out["vwap"] = compute_vwap(df)
    return out
