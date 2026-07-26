"""Generate the README charts (SVG + PNG, light and dark themes) from repo data.

Usage:
    python scripts/make_charts.py                     # writes into assets/
    python scripts/make_charts.py --assets-dir /tmp/x  # preview elsewhere

Inputs (see README "Data"): data/spy_1min.parquet is required;
data/es_1min.parquet is optional (without it the ES-vs-SPY chart is skipped).
The SPY equity curves and the walk-forward variant returns are recomputed
here from the same functions the reports use, so a fresh clone needs no
intermediate files.

Palette: the dataviz reference palette (CVD-validated in both modes).
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest import CostModel, run_backtest  # noqa: E402
from src.noise_area import filter_rth, session_closes  # noqa: E402
from src.run_walkforward import (  # noqa: E402
    CONTROL, WF_START, _paper_distance, quarterly_marks, trailing_sharpe,
    variant_returns,
)

ET = "America/New_York"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

THEMES = {
    "light": dict(bg="#ffffff", ink="#0b0b0b", sub="#52514e", grid="#e6e5e0",
                  blue="#2a78d6", green="#008300", magenta="#e87ba4",
                  orange="#eb6834", gray="#8a8983"),
    "dark": dict(bg="#0d1117", ink="#ffffff", sub="#c3c2b7", grid="#2c2c2a",
                 blue="#3987e5", green="#008300", magenta="#d55181",
                 orange="#d95926", gray="#8a8983"),
}


def style(ax, t, ylog=False):
    ax.set_facecolor(t["bg"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(t["grid"])
    ax.tick_params(colors=t["sub"], labelsize=9)
    ax.yaxis.grid(True, color=t["grid"], linewidth=0.7)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    if ylog:
        ax.set_yscale("log")


def save(fig, name, t, assets_dir):
    """Save SVG (crisp on the web) and PNG (the GitHub mobile app does not
    render SVG)."""
    fig.patch.set_facecolor(t["bg"])
    base = os.path.join(assets_dir, name.removesuffix(".svg"))
    fig.savefig(base + ".svg", format="svg", bbox_inches="tight",
                facecolor=t["bg"])
    fig.savefig(base + ".png", format="png", dpi=160, bbox_inches="tight",
                facecolor=t["bg"])
    plt.close(fig)


def growth(returns: pd.Series) -> pd.Series:
    return (1 + returns.fillna(0)).cumprod()


def load_data(spy_path, es_path, wf_cache):
    """Recompute everything the charts need from the 1-minute bars.

    The SPY equity curves use exactly the parameters of the replication
    (default costs, 100k initial equity) reported in reports/validation.md.
    """
    if not os.path.exists(spy_path):
        sys.exit(f"{spy_path} is missing — run src.download_alpaca first "
                 "(see README, Quickstart).")
    d = {}
    spy = filter_rth(pd.read_parquet(spy_path))
    d["spy_close"] = session_closes(spy)
    for mode in ("final", "base"):
        d[f"eq_{mode}"] = run_backtest(
            spy, exit_mode=mode, costs=CostModel()
        ).equity
    d["wf_rets"] = variant_returns(spy, wf_cache)
    d["es_path"] = es_path
    return d


# ---------------------------------------------------------------- fig 1
def fig_equity(d, mode, t, assets_dir):
    f = d["eq_final"] / d["eq_final"].iloc[0]
    b = d["eq_base"] / d["eq_base"].iloc[0]
    bh = d["spy_close"] / d["spy_close"].iloc[0]

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    style(ax, t, ylog=True)
    ax.plot(f.index, f, color=t["blue"], lw=2, label="Strategy — final exit (paper)")
    ax.plot(b.index, b, color=t["green"], lw=2, label="Strategy — base exit")
    ax.plot(bh.index, bh, color=t["gray"], lw=1.6, ls=(0, (4, 2)), label="SPY buy & hold")
    ax.set_yticks([1, 1.5, 2, 2.5, 3], labels=["1.0x", "1.5x", "2.0x", "2.5x", "3.0x"])
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.legend(frameon=False, labelcolor=t["ink"], fontsize=9, loc="upper left")
    ax.set_title("Growth of $1 — SPY, Jul 2020 → Jul 2026 (net of costs, log scale)",
                 color=t["ink"], fontsize=11, loc="left", pad=12)
    save(fig, f"equity_spy_{mode}.svg", t, assets_dir)


# ---------------------------------------------------------------- fig 2
def fig_yearly(d, mode, t, assets_dir):
    strat = d["eq_final"].pct_change()
    bh = d["spy_close"].pct_change()
    ys = strat.groupby(strat.index.year).apply(lambda r: (1 + r).prod() - 1)
    yb = bh.groupby(bh.index.year).apply(lambda r: (1 + r).prod() - 1)
    years = ys.index.astype(int)

    x = np.arange(len(years))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    style(ax, t)
    ax.bar(x - w / 2, ys.to_numpy(), w, color=t["blue"], label="Strategy (final)")
    ax.bar(x + w / 2, yb.to_numpy(), w, color=t["gray"], label="SPY buy & hold")
    ax.axhline(0, color=t["sub"], lw=0.8)
    ax.set_xticks(x, labels=[str(y) for y in years])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    ax.legend(frameon=False, labelcolor=t["ink"], fontsize=9, loc="upper right")
    ax.set_title("Return per year — the edge was there (2020-24) and compressed (2025-26)",
                 color=t["ink"], fontsize=11, loc="left", pad=12)
    ax.set_ylim(top=0.40)
    ax.annotate("2022: SPY -19.5%\nstrategy +25.8%", xy=(2, 0.262),
                xytext=(1.55, 0.335), color=t["sub"], fontsize=8.5)
    save(fig, f"yearly_{mode}.svg", t, assets_dir)


# ---------------------------------------------------------------- fig 3
def fig_es_vs_spy(d, mode, t, assets_dir, cache={}):
    if "es" not in cache:
        if not os.path.exists(d["es_path"]):
            print(f"  skipping es_vs_spy: {d['es_path']} not available")
            return
        es = filter_rth(pd.read_parquet(d["es_path"]))
        res = run_backtest(es, exit_mode="final", costs=CostModel.es_futures(0.25),
                           unit_multiplier=50.0, initial_equity=1_000_000.0)
        cache["es"] = res.equity
    common = pd.Timestamp("2024-07-01", tz=ET)
    es_eq = cache["es"][cache["es"].index >= common]
    spy_eq = d["eq_final"][d["eq_final"].index >= common]
    es_g = es_eq / es_eq.iloc[0]
    spy_g = spy_eq / spy_eq.iloc[0]

    fig, ax = plt.subplots(figsize=(9.2, 4.2))
    style(ax, t)
    ax.plot(es_g.index, es_g, color=t["blue"], lw=2)
    ax.plot(spy_g.index, spy_g, color=t["magenta"], lw=2)
    ax.text(es_g.index[-1], es_g.iloc[-1], "  ES (futures, IB)", color=t["ink"],
            fontsize=9, va="center")
    ax.text(spy_g.index[-1], spy_g.iloc[-1] - 0.012, "  SPY (IEX)", color=t["ink"],
            fontsize=9, va="center")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.2f}x")
    ax.set_xlim(es_g.index[0], es_g.index[-1] + pd.Timedelta(days=120))
    ax.set_title("Same strategy, two independent data sources — correlation 0.97: "
                 "the recent decline is real", color=t["ink"], fontsize=11,
                 loc="left", pad=12)
    save(fig, f"es_vs_spy_{mode}.svg", t, assets_dir)


# ---------------------------------------------------------------- fig 4
def fig_maroy(d, mode, t, assets_dir):
    rets = d["wf_rets"]
    is_rets = rets[rets.index < pd.Timestamp("2024-01-01", tz=ET)]
    sharpe = (is_rets.mean() / is_rets.std() * np.sqrt(252)).round(2)

    exits, lbs, ivs = ["base", "final", "vwap"], [7, 14, 28], [15, 30, 60]
    cmap = LinearSegmentedColormap.from_list(
        "seq", ["#dbe7f6", "#2a78d6", "#123a68"] if mode == "light"
        else ["#16283f", "#3987e5", "#bcd7f7"]
    )
    vmin, vmax = sharpe.min(), sharpe.max()

    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.4), sharey=True)
    for ax, ex in zip(axes, exits):
        m = np.array([[sharpe[f"{ex}/{lb}/{iv}"] for iv in ivs] for lb in lbs])
        im = ax.imshow(m, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
        ax.set_facecolor(t["bg"])
        ax.set_xticks(range(3), labels=[f"{iv}m" for iv in ivs])
        ax.set_yticks(range(3), labels=[f"{lb}d" for lb in lbs])
        ax.tick_params(colors=t["sub"], labelsize=9, length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(f"{ex} exit", color=t["ink"], fontsize=10)
        for i in range(3):
            for j in range(3):
                dark_cell = (m[i, j] - vmin) / (vmax - vmin) > 0.55
                ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center", fontsize=9,
                        color="#ffffff" if dark_cell else ("#0b0b0b" if mode == "light" else "#e6e6e6"))
        if ex == "final":
            ax.add_patch(plt.Rectangle((0.5, 0.5), 1, 1, fill=False,
                                       edgecolor=t["orange"], lw=2.2))
    axes[0].set_ylabel("lookback", color=t["sub"], fontsize=9)
    fig.suptitle("Maróy grid: in-sample Sharpe of the 27 variants — the paper's config wins (boxed)",
                 color=t["ink"], fontsize=11, x=0.02, ha="left")
    fig.subplots_adjust(top=0.78)
    save(fig, f"maroy_grid_{mode}.svg", t, assets_dir)


# ---------------------------------------------------------------- fig 5
def fig_walkforward(d, mode, t, assets_dir):
    rets = d["wf_rets"]
    marks = quarterly_marks(rets.index)
    picks = []
    for mk in marks:
        sr = trailing_sharpe(rets, mk)
        cands = sorted(sr[sr == sr.max()].index, key=_paper_distance)
        picks.append((mk, cands[0]))
    wf = pd.Series(np.nan, index=rets.index[rets.index >= WF_START])
    for i, (mk, name) in enumerate(picks):
        end = picks[i + 1][0] if i + 1 < len(picks) else None
        seg = rets.loc[mk:, name]
        if end is not None:
            seg = seg[seg.index < end]
        wf.loc[seg.index] = seg
    wf = wf.dropna()
    ctrl = rets.loc[wf.index, CONTROL]

    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    style(ax, t)
    g_ctrl, g_wf = growth(ctrl), growth(wf)
    ax.plot(g_ctrl.index, g_ctrl, color=t["blue"], lw=2,
            label="Paper config, fixed (Sharpe 0.92)")
    ax.plot(g_wf.index, g_wf, color=t["orange"], lw=2,
            label="Quarterly walk-forward (Sharpe 0.57)")
    for mk, _ in picks[1:]:
        ax.axvline(mk, color=t["grid"], lw=0.6)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.1f}x")
    ax.legend(frameon=False, labelcolor=t["ink"], fontsize=9, loc="upper left")
    ax.set_title("Quarterly reselection vs fixed parameters — adaptivity destroys value",
                 color=t["ink"], fontsize=11, loc="left", pad=12)
    save(fig, f"walkforward_{mode}.svg", t, assets_dir)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--assets-dir", default=ASSETS)
    p.add_argument("--spy", default=os.path.join(ROOT, "data/spy_1min.parquet"))
    p.add_argument("--es", default=os.path.join(ROOT, "data/es_1min.parquet"))
    p.add_argument("--wf-cache",
                   default=os.path.join(ROOT, "data/wf_variant_returns.parquet"))
    args = p.parse_args()

    os.makedirs(args.assets_dir, exist_ok=True)
    d = load_data(args.spy, args.es, args.wf_cache)
    for mode, t in THEMES.items():
        plt.rcParams.update({"font.size": 10, "text.color": t["ink"],
                             "axes.labelcolor": t["sub"]})
        fig_equity(d, mode, t, args.assets_dir)
        fig_yearly(d, mode, t, args.assets_dir)
        fig_es_vs_spy(d, mode, t, args.assets_dir)
        fig_maroy(d, mode, t, args.assets_dir)
        fig_walkforward(d, mode, t, args.assets_dir)
        print(f"theme {mode}: charts written to {args.assets_dir}")


if __name__ == "__main__":
    main()
