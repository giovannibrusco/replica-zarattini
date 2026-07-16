"""Esecuzione del walk-forward PROTOCOL_WALKFORWARD.md (commit 3ae8b7c).

Fase 1: rendimenti giornalieri netti full-sample delle 27 varianti
        (cache in data/wf_variant_returns.parquet: 27 backtest costosi)
Fase 2: selezione trimestrale meccanica su Sharpe trailing 252g
Fase 3: confronto con il controllo fisso sul periodo comune + report

Uso:
    python -m src.run_walkforward --data data/spy_1min.parquet \
        --out reports/walkforward_experiment.md
"""

from __future__ import annotations

import argparse
import io
import os

import numpy as np
import pandas as pd

from .backtest import CostModel, run_backtest
from .noise_area import filter_rth
from .stats import TRADING_DAYS

ET = "America/New_York"

EVAL_START = pd.Timestamp("2020-10-01", tz=ET)   # dopo il warmup indicatori
WF_START = pd.Timestamp("2021-10-01", tz=ET)     # primo trimestre applicato
WINDOW = 252
MIN_OBS = 200

EXITS = ["base", "final", "vwap"]
LOOKBACKS = [7, 14, 28]
INTERVALS = [15, 30, 60]
CONTROL = "final/14/30"


def _paper_distance(name: str) -> tuple:
    ex, lb, iv = name.split("/")
    return (ex != "final", abs(int(lb) - 14), abs(int(iv) - 30))


def variant_returns(bars: pd.DataFrame, cache: str) -> pd.DataFrame:
    """Matrice giorni x 27 varianti dei rendimenti giornalieri netti."""
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    cols = {}
    for ex in EXITS:
        for lb in LOOKBACKS:
            for iv in INTERVALS:
                name = f"{ex}/{lb}/{iv}"
                res = run_backtest(
                    bars, exit_mode=ex, lookback=lb, check_interval_min=iv,
                    costs=CostModel(),
                )
                eq = res.equity[res.equity.index >= EVAL_START]
                cols[name] = eq.pct_change()
                print(f"  {name}: ok ({len(eq)} giorni)")
    df = pd.DataFrame(cols).dropna(how="all")
    df.to_parquet(cache)
    return df


def quarterly_marks(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Primi giorni di trading di ogni trimestre >= WF_START."""
    q = pd.Series(index, index=index).groupby(
        [index.year, index.quarter]
    ).first()
    return [d for d in q if d >= WF_START]


def trailing_sharpe(rets: pd.DataFrame, end_excl: pd.Timestamp) -> pd.Series:
    win = rets[rets.index < end_excl].tail(WINDOW)
    valid = win.count() >= MIN_OBS
    sr = win.mean() / win.std() * np.sqrt(TRADING_DAYS)
    return sr.where(valid)


def _perf(r: pd.Series) -> dict:
    r = r.dropna()
    sr = r.mean() / r.std() * np.sqrt(TRADING_DAYS)
    eq = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    return {
        "sharpe": sr,
        "cagr": eq.iloc[-1] ** (1 / years) - 1,
        "max_dd": (eq / eq.cummax() - 1).min(),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/spy_1min.parquet")
    p.add_argument("--cache", default="data/wf_variant_returns.parquet")
    p.add_argument("--out", default="reports/walkforward_experiment.md")
    args = p.parse_args()

    rth = filter_rth(pd.read_parquet(args.data)).sort_index()
    rets = variant_returns(rth, args.cache)

    # --- selezione trimestrale ---
    marks = quarterly_marks(rets.index)
    picks: list[tuple[pd.Timestamp, str]] = []
    for mark in marks:
        sr = trailing_sharpe(rets, mark)
        best = sr.max()
        cands = sorted(sr[sr == best].index, key=_paper_distance)
        picks.append((mark, cands[0]))

    # --- ricostruzione rendimenti walk-forward ---
    wf = pd.Series(np.nan, index=rets.index[rets.index >= WF_START])
    for i, (mark, name) in enumerate(picks):
        end = picks[i + 1][0] if i + 1 < len(picks) else None
        seg = rets.loc[mark:, name] if end is None else rets.loc[mark:, name][rets.loc[mark:].index < end]
        wf.loc[seg.index] = seg
    wf = wf.dropna()
    ctrl = rets.loc[wf.index, CONTROL].dropna()

    pw, pc = _perf(wf), _perf(ctrl)
    w1 = pw["sharpe"] > pc["sharpe"]
    switches = sum(1 for i in range(1, len(picks)) if picks[i][1] != picks[i - 1][1])

    print(f"\nWalk-forward: Sharpe {pw['sharpe']:+.2f}  CAGR {pw['cagr']:+.1%}  DD {pw['max_dd']:.1%}")
    print(f"Controllo:    Sharpe {pc['sharpe']:+.2f}  CAGR {pc['cagr']:+.1%}  DD {pc['max_dd']:.1%}")
    print(f"W1 {'PASS' if w1 else 'FAIL'} | switch: {switches}/{len(picks) - 1}")

    # --- report ---
    buf = io.StringIO()
    w = buf.write
    w("# Esperimento walk-forward — risultati (protocollo commit 3ae8b7c)\n\n")
    w(f"Periodo valutato: {wf.index[0].date()} → {wf.index[-1].date()} "
      f"({len(wf)} giorni). Selezione trimestrale su Sharpe trailing "
      f"{WINDOW}g, universo = 27 varianti della lista chiusa.\n\n")

    w("## Confronto (stesso periodo)\n\n")
    tab = pd.DataFrame(
        {
            "Walk-forward": {k: v for k, v in pw.items()},
            "Controllo (paper fisso)": {k: v for k, v in pc.items()},
        }
    ).T
    tab["sharpe"] = tab["sharpe"].map("{:.2f}".format)
    tab["cagr"] = tab["cagr"].map("{:+.1%}".format)
    tab["max_dd"] = tab["max_dd"].map("{:.1%}".format)
    w(tab.to_markdown() + "\n\n")
    w(f"**W1 (Sharpe WF > controllo): {'PASS' if w1 else 'FAIL'}**\n\n")

    w("## Varianti selezionate per trimestre\n\n")
    sel = pd.DataFrame(picks, columns=["trimestre", "variante"])
    sel["trimestre"] = sel["trimestre"].dt.date
    w(sel.to_markdown(index=False) + "\n\n")
    w(f"Switch effettuati: {switches} su {len(picks) - 1} riselezioni.\n\n")

    w("## Per anno (Sharpe)\n\n")
    ya = pd.DataFrame(
        {
            "Walk-forward": wf.groupby(wf.index.year).apply(
                lambda r: r.mean() / r.std() * np.sqrt(TRADING_DAYS)
            ),
            "Controllo": ctrl.groupby(ctrl.index.year).apply(
                lambda r: r.mean() / r.std() * np.sqrt(TRADING_DAYS)
            ),
        }
    ).round(2)
    w(ya.to_markdown() + "\n\n")

    if w1:
        w("## Verdetto\n\nW1 superato: l'adattivita' aggiunge valore su questo "
          "campione. Esito pilota da confermare sulla fase ES.\n")
    else:
        w("## Verdetto\n\nW1 fallito: la riselezione periodica non batte la "
          "config fissa del paper. Come da protocollo il tema si chiude fino "
          "alla fase ES; nessun altro design verra' provato su questi dati.\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(buf.getvalue())
    print(f"Report scritto in {args.out}")


if __name__ == "__main__":
    main()
