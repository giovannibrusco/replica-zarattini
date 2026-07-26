"""Run the full validation plan and generate the markdown report.

Usage:
    python -m src.run_validation --data data/spy_1min.parquet \
        --vix data/vix_history.csv --out reports/validation.md

VIX data (optional) can be downloaded from:
    https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
"""

from __future__ import annotations

import argparse
import io
import os

import pandas as pd

from .backtest import CostModel, run_backtest
from .noise_area import filter_rth, session_closes
from .stats import (
    performance_summary,
    regime_table,
    trade_stats,
    yearly_table,
)


def _fmt_perf(perf: dict, ts: dict | None = None) -> dict:
    row = {
        "Total return": f"{perf['total_return']:+.1%}",
        "CAGR": f"{perf['cagr']:+.2%}",
        "Ann. vol": f"{perf['ann_vol']:.1%}",
        "Sharpe": f"{perf['sharpe']:.2f}",
        "Max DD": f"{perf['max_drawdown']:.1%}",
    }
    if "alpha_ann" in perf:
        row["Ann. alpha"] = f"{perf['alpha_ann']:+.1%}"
        row["Alpha t-stat"] = f"{perf['alpha_tstat']:.2f}"
        row["Beta"] = f"{perf['beta']:.2f}"
    if ts:
        row.update(
            {
                "Trades": str(ts["n_trades"]),
                "Win rate": f"{ts['win_rate']:.1%}",
                "Payoff": f"{ts['payoff_ratio']:.2f}",
                "Expectancy (bps)": f"{ts['expectancy_bps']:+.2f}",
                "Max losing streak": str(ts["max_losing_streak"]),
            }
        )
    return row


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/spy_1min.parquet")
    p.add_argument("--vix", default="data/vix_history.csv")
    p.add_argument("--out", default="reports/validation.md")
    args = p.parse_args()

    rth = filter_rth(pd.read_parquet(args.data))
    spy_ret = session_closes(rth).pct_change().dropna()

    buf = io.StringIO()
    w = buf.write
    w("# Replication validation — SPY (Alpaca IEX data)\n\n")
    days = rth.index.normalize().unique()
    w(f"Sample: **{days[0].date()} → {days[-1].date()}** "
      f"({len(days)} days, {len(rth):,} 1-min RTH bars).\n\n")

    # --- base vs final vs buy&hold ---
    results = {}
    rows = {}
    for mode in ("base", "final"):
        res = run_backtest(rth, exit_mode=mode, costs=CostModel())
        results[mode] = res
        rows[mode] = _fmt_perf(
            performance_summary(res.daily_returns, spy_ret),
            trade_stats(res.trades),
        )
    rows["SPY buy&hold"] = _fmt_perf(performance_summary(spy_ret))
    w("## Base vs Final vs passive benchmark\n\n")
    w(pd.DataFrame(rows).fillna("—").to_markdown() + "\n\n")

    w("Expected external benchmarks: paper (SPY 2007-24) Sharpe ~1.33, alpha ~19.6%, "
      "beta ~0; Quantitativo replication (ES) ~+2 bps/trade, win rate ~36%, "
      "payoff ~2.1.\n\n")

    # --- per year ---
    w("## Temporal robustness (final variant)\n\n")
    yt = yearly_table(results["final"].daily_returns, spy_ret)
    ytb = yearly_table(spy_ret)
    tab = pd.DataFrame(
        {
            "Strategy": yt["total_return"].map("{:+.1%}".format),
            "Sharpe": yt["sharpe"].map("{:.2f}".format),
            "Ann. alpha": yt["alpha_ann"].map("{:+.1%}".format),
            "SPY B&H": ytb["total_return"].map("{:+.1%}".format),
        }
    )
    tab.index = tab.index.astype(int)
    w(tab.to_markdown() + "\n\n")

    # --- VIX regimes ---
    if os.path.exists(args.vix):
        vix = pd.read_csv(args.vix, parse_dates=["DATE"], date_format="%m/%d/%Y")
        vix = vix.set_index("DATE")["CLOSE"]
        vix.index = vix.index.tz_localize("America/New_York")
        rt = regime_table(results["final"].daily_returns, vix)
        w("## VIX regimes (final variant)\n\n")
        rtab = pd.DataFrame(
            {
                "Total return": rt["total_return"].map("{:+.1%}".format),
                "Sharpe": rt["sharpe"].map("{:.2f}".format),
                "Days": rt["n_days"].astype(int),
            }
        )
        w(rtab.to_markdown() + "\n\n")

    # --- cost sensitivity ---
    w("## Slippage sensitivity (final variant)\n\n")
    srows = {}
    for slip in (0.0, 0.005, 0.01):
        r = run_backtest(rth, exit_mode="final", costs=CostModel(slippage_per_unit=slip))
        pf = performance_summary(r.daily_returns, spy_ret)
        t = trade_stats(r.trades)
        srows[f"${slip:.3f}/share"] = {
            "CAGR": f"{pf['cagr']:+.1%}",
            "Sharpe": f"{pf['sharpe']:.2f}",
            "Expectancy (bps)": f"{t['expectancy_bps']:+.2f}",
            "Win rate": f"{t['win_rate']:.1%}",
        }
    w(pd.DataFrame(srows).T.to_markdown() + "\n\n")

    # --- caveats ---
    w(
        "## Caveats\n\n"
        "- **IEX feed** (~3% of volume): approximated VWAP (which affects the "
        "final exit) and scattered missing minutes (the engine uses the last "
        "price available at the check).\n"
        "- **Sample starts 2020-07** (Alpaca free-tier limit): no 2008 and no "
        "pre-COVID period; the comparison with the paper (2007-24) is "
        "therefore an order-of-magnitude one.\n"
        "- IB commissions $0.0035/share (min $0.35) as in the paper; baseline "
        "slippage 0.\n"
        "- In the VIX>30 buckets the sample is tiny: no conclusions drawn.\n"
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(buf.getvalue())
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
