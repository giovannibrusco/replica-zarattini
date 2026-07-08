"""Generatori di barre sintetiche per i test."""

from __future__ import annotations

import numpy as np
import pandas as pd

ET = "America/New_York"
BARS_PER_DAY = 390  # 09:30 .. 15:59


def make_day(date: str, open_px: float, closes) -> pd.DataFrame:
    """Un giorno RTH di 390 barre. `closes` e' uno scalare o un array di 390.

    open della prima barra = open_px (open RTH del giorno); high/low = close
    (barre 'piatte', cosi' il VWAP e' la media pesata dei close), volume 1000.
    """
    idx = pd.date_range(f"{date} 09:30", periods=BARS_PER_DAY, freq="1min", tz=ET)
    closes = np.full(BARS_PER_DAY, closes, dtype=float) if np.isscalar(closes) else np.asarray(closes, dtype=float)
    assert len(closes) == BARS_PER_DAY
    opens = np.concatenate([[open_px], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1000.0,
        },
        index=idx,
    )


def stack_days(*days: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(days).sort_index()


def path_step(before: float, after: float, switch_minute: int) -> np.ndarray:
    """Percorso a gradino: `before` fino al minuto switch (escluso), poi `after`.

    switch_minute e' l'offset in minuti da 09:30 (es. 10:00 -> 30).
    """
    path = np.full(BARS_PER_DAY, before, dtype=float)
    path[switch_minute:] = after
    return path
