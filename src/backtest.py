"""Engine di backtest event-driven per la strategia Noise Area.

Regole (spec):
- Check di entry/exit SOLO ai timestamp di 30 minuti: 10:00, 10:30, ..., 15:30.
  Il prezzo usato e' il close della barra a 1 minuto etichettata al check time.
- Entry: prezzo > Upper_t -> LONG; prezzo < Lower_t -> SHORT. Flip consentito.
- Exit variante "base":   long esce se prezzo < Lower_t (banda opposta);
                          short esce se prezzo > Upper_t.
- Exit variante "final":  long esce se prezzo < max(VWAP_t, Upper_t);
                          short esce se prezzo > min(VWAP_t, Lower_t)
  (rientro nella Noise Area oppure attraversamento del VWAP di giornata).
- Chiusura forzata di tutto sull'ultima barra RTH (15:59, prezzo di close
  della sessione): zero overnight.
- Sizing: vol targeting 2% con cap di leva 4x, calcolato all'entry con
  l'equity corrente (compounding).

Costi (parametrici, vedi CostModel): per azioni commissione per share +
slippage in dollari per share; per futures commissione+fee per contratto +
slippage in tick. Applicati per transazione (entry e exit separatamente).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd

from .noise_area import build_indicators, session_closes, _day_key
from .sizing import (
    MAX_LEVERAGE,
    VOL_LOOKBACK,
    VOL_TARGET,
    daily_sigma,
    target_units,
)

# griglia dei check: 10:00, 10:30, ..., 15:30 — CONGELATA da spec
CHECK_TIMES = [time(h, m) for h in range(10, 16) for m in (0, 30)]
FORCED_EXIT_TIME = time(15, 59)


@dataclass
class CostModel:
    """Costi per transazione (una gamba; un round trip = due transazioni)."""

    commission_per_unit: float = 0.0035  # $/share (IB, come nel paper) o $/contratto
    fees_per_unit: float = 0.0           # exchange+regulatory (futures)
    slippage_per_unit: float = 0.0       # $ per unita' per transazione
    min_commission: float = 0.35         # minimo per ordine (IB stocks)

    def commission(self, units: int) -> float:
        return max(self.commission_per_unit * units, self.min_commission) + (
            self.fees_per_unit * units
        )

    @staticmethod
    def es_futures(slippage_ticks: float = 0.25, micro: bool = False) -> "CostModel":
        """Costi spec per ES/MES: commissione+fees per contratto, slippage in tick."""
        tick_value = 1.25 if micro else 12.50  # 0.25 punti indice
        return CostModel(
            commission_per_unit=0.25 if micro else 0.85,
            fees_per_unit=0.35 if micro else 1.40,
            slippage_per_unit=slippage_ticks * tick_value,
            min_commission=0.0,
        )


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series          # equity a fine giornata (sempre flat overnight)
    daily_returns: pd.Series = field(init=False)

    def __post_init__(self) -> None:
        self.daily_returns = self.equity.pct_change().fillna(0.0)


def run_backtest(
    bars: pd.DataFrame,
    initial_equity: float = 100_000.0,
    exit_mode: str = "final",
    costs: CostModel | None = None,
    unit_multiplier: float = 1.0,  # 1 per azioni; 50 per ES, 5 per MES
    lookback: int = 14,
    vol_target: float = VOL_TARGET,
    max_leverage: float = MAX_LEVERAGE,
    vol_lookback: int = VOL_LOOKBACK,
) -> BacktestResult:
    """Esegue il backtest su barre 1-minuto RTH (vedi noise_area per il formato).

    exit_mode: "base" (banda opposta) o "final" (max/min di VWAP e banda di entry).
    """
    if exit_mode not in ("base", "final"):
        raise ValueError("exit_mode deve essere 'base' o 'final'")
    if costs is None:
        costs = CostModel()

    ind = build_indicators(bars, lookback=lookback)
    closes_d = session_closes(ind)
    sigma_d = daily_sigma(closes_d, lookback=vol_lookback)

    equity = initial_equity
    trades: list[dict] = []
    equity_by_day: dict[pd.Timestamp, float] = {}

    # posizione corrente
    side = 0  # +1 long, -1 short, 0 flat
    units = 0
    entry_px = 0.0
    entry_time = None

    def _exec_price(px: float, buy: bool) -> float:
        slip = costs.slippage_per_unit / unit_multiplier
        return px + slip if buy else px - slip

    def _close_position(px: float, ts: pd.Timestamp, reason: str) -> None:
        nonlocal equity, side, units, entry_px, entry_time
        exec_px = _exec_price(px, buy=(side < 0))
        gross = side * units * (exec_px - entry_px) * unit_multiplier
        comm = costs.commission(units)
        equity += gross - comm
        trades.append(
            {
                "entry_time": entry_time,
                "exit_time": ts,
                "side": "long" if side > 0 else "short",
                "units": units,
                "entry_px": entry_px,
                "exit_px": exec_px,
                "gross_pnl": gross,
                "costs": comm + trades_open_cost[0],
                "net_pnl": gross - comm - trades_open_cost[0],
                "exit_reason": reason,
                "equity_after": equity,
            }
        )
        side, units, entry_px, entry_time = 0, 0, 0.0, None

    def _open_position(new_side: int, px: float, ts: pd.Timestamp, sd: float) -> None:
        nonlocal equity, side, units, entry_px, entry_time
        exec_px = _exec_price(px, buy=(new_side > 0))
        n = target_units(
            equity, sd, exec_px * unit_multiplier, vol_target, max_leverage
        )
        if n <= 0:
            return
        comm = costs.commission(n)
        equity -= comm
        trades_open_cost[0] = comm
        side, units, entry_px, entry_time = new_side, n, exec_px, ts

    trades_open_cost = [0.0]  # costo di apertura del trade corrente

    for day, day_bars in ind.groupby(_day_key(ind.index)):
        sd = sigma_d.get(day, np.nan)
        by_time = day_bars.set_index(day_bars.index.time)

        for t in CHECK_TIMES:
            if t not in by_time.index:
                continue
            row = by_time.loc[t]
            px, upper, lower, vwap = (
                row["close"], row["upper"], row["lower"], row["vwap"]
            )
            if not np.isfinite(upper) or not np.isfinite(lower):
                continue  # warmup o dati insufficienti: non si opera
            ts = pd.Timestamp.combine(day.date(), t).tz_localize(day_bars.index.tz)

            long_sig = px > upper
            short_sig = px < lower

            if side > 0:
                if short_sig:  # flip long -> short
                    _close_position(px, ts, "flip")
                    if np.isfinite(sd):
                        _open_position(-1, px, ts, sd)
                elif (exit_mode == "base" and px < lower) or (
                    exit_mode == "final" and px < max(vwap, upper)
                ):
                    _close_position(px, ts, "trail")
            elif side < 0:
                if long_sig:  # flip short -> long
                    _close_position(px, ts, "flip")
                    if np.isfinite(sd):
                        _open_position(1, px, ts, sd)
                elif (exit_mode == "base" and px > upper) or (
                    exit_mode == "final" and px > min(vwap, lower)
                ):
                    _close_position(px, ts, "trail")
            else:
                if (long_sig or short_sig) and np.isfinite(sd):
                    _open_position(1 if long_sig else -1, px, ts, sd)

        # chiusura forzata a fine sessione (zero overnight)
        if side != 0:
            last = day_bars.iloc[-1]
            ts = day_bars.index[-1]
            _close_position(last["close"], ts, "eod")

        equity_by_day[day] = equity

    trades_df = pd.DataFrame(trades)
    equity_series = pd.Series(equity_by_day, name="equity").sort_index()
    return BacktestResult(trades=trades_df, equity=equity_series)
