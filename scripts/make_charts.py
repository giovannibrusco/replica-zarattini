"""Genera i grafici del README (SVG, tema chiaro e scuro) dai dati del repo.

Uso:  python scripts/make_charts.py
Richiede i parquet in data/ (equity SPY gia' salvate, ES ricalcolato al volo).
Palette: reference palette del metodo dataviz (validata CVD in entrambi i modi).
"""

from __future__ import annotations

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
)

ET = "America/New_York"
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

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


def save(fig, name, t):
    """Salva SVG (web, nitido) e PNG (app mobile GitHub: non rende gli SVG)."""
    fig.patch.set_facecolor(t["bg"])
    base = os.path.join(ASSETS, name.removesuffix(".svg"))
    fig.savefig(base + ".svg", format="svg", bbox_inches="tight",
                facecolor=t["bg"])
    fig.savefig(base + ".png", format="png", dpi=160, bbox_inches="tight",
                facecolor=t["bg"])
    plt.close(fig)


def growth(returns: pd.Series) -> pd.Series:
    return (1 + returns.fillna(0)).cumprod()


def load_data():
    d = {}
    d["eq_final"] = pd.read_parquet("data/equity_final.parquet")["equity"]
    d["eq_base"] = pd.read_parquet("data/equity_base.parquet")["equity"]
    spy = filter_rth(pd.read_parquet("data/spy_1min.parquet"))
    d["spy_close"] = session_closes(spy)
    d["wf_rets"] = pd.read_parquet("data/wf_variant_returns.parquet")
    d["spy_bars"] = spy
    return d


# ---------------------------------------------------------------- fig 1
def fig_equity(d, mode, t):
    f = d["eq_final"] / d["eq_final"].iloc[0]
    b = d["eq_base"] / d["eq_base"].iloc[0]
    bh = d["spy_close"] / d["spy_close"].iloc[0]

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    style(ax, t, ylog=True)
    ax.plot(f.index, f, color=t["blue"], lw=2, label="Strategia — exit final (paper)")
    ax.plot(b.index, b, color=t["green"], lw=2, label="Strategia — exit base")
    ax.plot(bh.index, bh, color=t["gray"], lw=1.6, ls=(0, (4, 2)), label="SPY buy & hold")
    ax.set_yticks([1, 1.5, 2, 2.5, 3], labels=["1.0x", "1.5x", "2.0x", "2.5x", "3.0x"])
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.legend(frameon=False, labelcolor=t["ink"], fontsize=9, loc="upper left")
    ax.set_title("Crescita di $1 — SPY, lug 2020 → lug 2026 (netto costi, scala log)",
                 color=t["ink"], fontsize=11, loc="left", pad=12)
    save(fig, f"equity_spy_{mode}.svg", t)


# ---------------------------------------------------------------- fig 2
def fig_yearly(d, mode, t):
    strat = d["eq_final"].pct_change()
    bh = d["spy_close"].pct_change()
    ys = strat.groupby(strat.index.year).apply(lambda r: (1 + r).prod() - 1)
    yb = bh.groupby(bh.index.year).apply(lambda r: (1 + r).prod() - 1)
    years = ys.index.astype(int)

    x = np.arange(len(years))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    style(ax, t)
    ax.bar(x - w / 2, ys.to_numpy(), w, color=t["blue"], label="Strategia (final)")
    ax.bar(x + w / 2, yb.to_numpy(), w, color=t["gray"], label="SPY buy & hold")
    ax.axhline(0, color=t["sub"], lw=0.8)
    ax.set_xticks(x, labels=[str(y) for y in years])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0%}")
    ax.legend(frameon=False, labelcolor=t["ink"], fontsize=9, loc="upper right")
    ax.set_title("Rendimento per anno — l'edge c'era (2020-24) e si è compresso (2025-26)",
                 color=t["ink"], fontsize=11, loc="left", pad=12)
    ax.set_ylim(top=0.40)
    ax.annotate("2022: SPY -19.5%\nstrategia +25.8%", xy=(2, 0.262),
                xytext=(1.55, 0.335), color=t["sub"], fontsize=8.5)
    save(fig, f"yearly_{mode}.svg", t)


# ---------------------------------------------------------------- fig 3
def fig_es_vs_spy(d, mode, t, cache={}):
    if "es" not in cache:
        es = filter_rth(pd.read_parquet("data/es_1min.parquet"))
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
    ax.set_title("Stessa strategia, due fonti dati indipendenti — correlazione 0.97: "
                 "il calo recente è reale", color=t["ink"], fontsize=11, loc="left", pad=12)
    save(fig, f"es_vs_spy_{mode}.svg", t)


# ---------------------------------------------------------------- fig 4
def fig_maroy(d, mode, t):
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
        ax.set_yticks(range(3), labels=[f"{lb}g" for lb in lbs])
        ax.tick_params(colors=t["sub"], labelsize=9, length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_title(f"exit {ex}", color=t["ink"], fontsize=10)
        for i in range(3):
            for j in range(3):
                dark_cell = (m[i, j] - vmin) / (vmax - vmin) > 0.55
                ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center", fontsize=9,
                        color="#ffffff" if dark_cell else ("#0b0b0b" if mode == "light" else "#e6e6e6"))
        if ex == "final":
            ax.add_patch(plt.Rectangle((0.5, 0.5), 1, 1, fill=False,
                                       edgecolor=t["orange"], lw=2.2))
    axes[0].set_ylabel("lookback", color=t["sub"], fontsize=9)
    fig.suptitle("Griglia Maróy: Sharpe in-sample delle 27 varianti — vince la config del paper (riquadro)",
                 color=t["ink"], fontsize=11, x=0.02, ha="left")
    fig.subplots_adjust(top=0.78)
    save(fig, f"maroy_grid_{mode}.svg", t)


# ---------------------------------------------------------------- fig 5
def fig_walkforward(d, mode, t):
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
    ax.plot(g_ctrl.index, g_ctrl, color=t["blue"], lw=2, label="Config paper, fissa (Sharpe 0.92)")
    ax.plot(g_wf.index, g_wf, color=t["orange"], lw=2, label="Walk-forward trimestrale (Sharpe 0.57)")
    for mk, _ in picks[1:]:
        ax.axvline(mk, color=t["grid"], lw=0.6)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.1f}x")
    ax.legend(frameon=False, labelcolor=t["ink"], fontsize=9, loc="upper left")
    ax.set_title("Riselezione trimestrale vs parametri fissi — l'adattività distrugge valore",
                 color=t["ink"], fontsize=11, loc="left", pad=12)
    save(fig, f"walkforward_{mode}.svg", t)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    d = load_data()
    for mode, t in THEMES.items():
        plt.rcParams.update({"font.size": 10, "text.color": t["ink"],
                             "axes.labelcolor": t["sub"]})
        fig_equity(d, mode, t)
        fig_yearly(d, mode, t)
        fig_es_vs_spy(d, mode, t)
        fig_maroy(d, mode, t)
        fig_walkforward(d, mode, t)
        print(f"tema {mode}: 5 SVG generati")


if __name__ == "__main__":
    main()
