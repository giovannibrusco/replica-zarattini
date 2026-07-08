"""Sanity check dei dati (punto 1 del piano di validazione).

Uso:
    python -m src.validate_data data/spy_1min.parquet

Controlli:
- numero di giorni e barre per giorno (390 attese per sessione piena,
  ~210 per le mezze sedute)
- duplicati nell'indice
- minuti mancanti dentro la sessione RTH
- barre a volume zero, prezzi non positivi
- spike di prezzo sospetti (rendimento 1-min > soglia)
"""

from __future__ import annotations

import sys

import pandas as pd

from .noise_area import filter_rth, _day_key

FULL_SESSION_BARS = 390
HALF_SESSION_BARS = 210
SPIKE_THRESHOLD = 0.02  # 2% in un minuto


def validate(df: pd.DataFrame, verbose: bool = True) -> dict:
    report: dict = {}
    dup = df.index.duplicated().sum()
    report["duplicate_index"] = int(dup)

    rth = filter_rth(df)
    report["total_bars"] = len(rth)
    per_day = rth.groupby(_day_key(rth.index)).size()
    report["n_days"] = len(per_day)
    report["first_day"] = str(per_day.index[0].date()) if len(per_day) else None
    report["last_day"] = str(per_day.index[-1].date()) if len(per_day) else None

    full = (per_day == FULL_SESSION_BARS).sum()
    near_full = per_day.between(FULL_SESSION_BARS - 10, FULL_SESSION_BARS - 1).sum()
    half = per_day.between(HALF_SESSION_BARS - 10, HALF_SESSION_BARS).sum()
    odd = per_day[
        ~per_day.between(FULL_SESSION_BARS - 10, FULL_SESSION_BARS)
        & ~per_day.between(HALF_SESSION_BARS - 10, HALF_SESSION_BARS)
    ]
    report["days_full_390"] = int(full)
    report["days_missing_few"] = int(near_full)
    report["days_half_session"] = int(half)
    report["days_odd_bar_count"] = {str(k.date()): int(v) for k, v in odd.items()}

    report["zero_volume_bars"] = int((rth["volume"] == 0).sum())
    report["nonpositive_prices"] = int((rth[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())

    ret = rth["close"].pct_change()
    day_changed = _day_key(rth.index).to_series().diff().ne(pd.Timedelta(0)).to_numpy()
    intraday_ret = ret[~day_changed]
    spikes = intraday_ret[intraday_ret.abs() > SPIKE_THRESHOLD]
    report["price_spikes"] = {str(k): round(float(v), 4) for k, v in spikes.items()}

    if verbose:
        for k, v in report.items():
            if isinstance(v, dict):
                print(f"{k}: {len(v)}")
                for kk, vv in list(v.items())[:20]:
                    print(f"    {kk}: {vv}")
            else:
                print(f"{k}: {v}")
    return report


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/spy_1min.parquet"
    validate(pd.read_parquet(path))
