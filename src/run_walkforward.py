"""Execution of the PROTOCOL_WALKFORWARD.md walk-forward (commit dbf73fb).

Phase 1: full-sample net daily returns of the 27 variants
         (cached in data/wf_variant_returns.parquet: 27 costly backtests)
Phase 2: mechanical quarterly selection on trailing 252-day Sharpe
Phase 3: comparison with the fixed control over the common period + report

Usage:
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

EVAL_START = pd.Timestamp("2020-10-01", tz=ET)   # after the indicator warmup
WF_START = pd.Timestamp("2021-10-01", tz=ET)     # first quarter applied
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
    """Days x 27 variants matrix of net daily returns."""
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
                print(f"  {name}: ok ({len(eq)} days)")
    df = pd.DataFrame(cols).dropna(how="all")
    df.to_parquet(cache)
    return df


def quarterly_marks(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """First trading day of each quarter >= WF_START."""
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

    # --- quarterly selection ---
    marks = quarterly_marks(rets.index)
    picks: list[tuple[pd.Timestamp, str]] = []
    for mark in marks:
        sr = trailing_sharpe(rets, mark)
        best = sr.max()
        cands = sorted(sr[sr == best].index, key=_paper_distance)
        picks.append((mark, cands[0]))

    # --- reconstruct the walk-forward returns ---
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
    print(f"Control:      Sharpe {pc['sharpe']:+.2f}  CAGR {pc['cagr']:+.1%}  DD {pc['max_dd']:.1%}")
    print(f"W1 {'PASS' if w1 else 'FAIL'} | switches: {switches}/{len(picks) - 1}")

    # --- report ---
    buf = io.StringIO()
    w = buf.write
    w("# Walk-forward experiment — results (protocol commit dbf73fb)\n\n")
    w(f"Period evaluated: {wf.index[0].date()} → {wf.index[-1].date()} "
      f"({len(wf)} days). Quarterly selection on trailing {WINDOW}-day "
      "Sharpe, universe = the 27 variants of the closed list.\n\n")

    w("## Comparison (same period)\n\n")
    tab = pd.DataFrame(
        {
            "Walk-forward": {k: v for k, v in pw.items()},
            "Control (paper, fixed)": {k: v for k, v in pc.items()},
        }
    ).T
    tab["sharpe"] = tab["sharpe"].map("{:.2f}".format)
    tab["cagr"] = tab["cagr"].map("{:+.1%}".format)
    tab["max_dd"] = tab["max_dd"].map("{:.1%}".format)
    w(tab.to_markdown() + "\n\n")
    w(f"**W1 (WF Sharpe > control): {'PASS' if w1 else 'FAIL'}**\n\n")

    w("## Variants selected per quarter\n\n")
    sel = pd.DataFrame(picks, columns=["quarter", "variant"])
    sel["quarter"] = sel["quarter"].dt.date
    w(sel.to_markdown(index=False) + "\n\n")
    w(f"Switches made: {switches} out of {len(picks) - 1} reselections.\n\n")

    w("## Per year (Sharpe)\n\n")
    ya = pd.DataFrame(
        {
            "Walk-forward": wf.groupby(wf.index.year).apply(
                lambda r: r.mean() / r.std() * np.sqrt(TRADING_DAYS)
            ),
            "Control": ctrl.groupby(ctrl.index.year).apply(
                lambda r: r.mean() / r.std() * np.sqrt(TRADING_DAYS)
            ),
        }
    ).round(2)
    w(ya.to_markdown() + "\n\n")

    if w1:
        w("## Verdict\n\nW1 met: adaptivity adds value on this sample. A pilot "
          "result, to be confirmed on the ES phase.\n")
    else:
        w("## Verdict\n\nW1 failed: periodic reselection does not beat the "
          "paper's fixed configuration. Per the protocol the topic is closed "
          "until the ES phase; no other design will be tried on this data.\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(buf.getvalue())
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
