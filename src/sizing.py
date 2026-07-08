"""Position sizing: volatility targeting con cap di leva.

Formula (spec, parametri CONGELATI):
    esposizione_target = Equity * vol_target / sigma_daily_lookback
    esposizione        = min(esposizione_target, max_leverage * Equity)
    unita'             = floor(esposizione / notional_per_unita')

Per SPY l'unita' e' 1 azione (notional = prezzo); per ES/MES e' un contratto
(notional = prezzo * moltiplicatore).
"""

from __future__ import annotations

import math

import pandas as pd

VOL_TARGET = 0.02      # 2% giornaliero — CONGELATO
MAX_LEVERAGE = 4.0     # 4x — CONGELATO
VOL_LOOKBACK = 14      # giorni — CONGELATO


def daily_sigma(session_close: pd.Series, lookback: int = VOL_LOOKBACK) -> pd.Series:
    """Vol giornaliera realizzata: std dei rendimenti close-to-close sugli
    ultimi `lookback` giorni, disponibile dal giorno successivo (shift 1,
    nessun look-ahead). ddof=1 (default pandas)."""
    rets = session_close.pct_change()
    return rets.rolling(lookback, min_periods=lookback).std().shift(1)


def target_units(
    equity: float,
    sigma_d: float,
    unit_notional: float,
    vol_target: float = VOL_TARGET,
    max_leverage: float = MAX_LEVERAGE,
) -> int:
    """Numero di unita' (azioni o contratti) per il vol targeting con cap di leva."""
    if not (sigma_d > 0.0) or not (unit_notional > 0.0) or equity <= 0.0:
        return 0
    exposure = min(equity * vol_target / sigma_d, max_leverage * equity)
    return int(math.floor(exposure / unit_notional))
