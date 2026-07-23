"""Esecuzione del protocollo PROTOCOL_MAROY.md (congelato nel commit 4d0a7cc).

Fasi, tutte meccaniche (nessuna discrezionalita'):
1. 27 varianti su in-sample (fino al 2023-12-31, valutazione dal 2020-10-01
   per uniformare il warmup tra lookback diversi)
2. Vincente = max Sharpe annualizzato netto IS (tie-break: vicinanza al paper)
3. Deflated Sharpe Ratio del vincente (N=27)
4. UNA valutazione out-of-sample (dal 2024-01-01) di vincente + controllo
5. Verdetto sui criteri C1/C2/C3 e report completo

Uso:
    python -m src.run_maroy --data data/spy_1min.parquet \
        --out reports/maroy_experiment.md
"""

from __future__ import annotations

import argparse
import io
import os

import numpy as np
import pandas as pd

from .backtest import CostModel, run_backtest
from .noise_area import filter_rth
from .stats import TRADING_DAYS, deflated_sharpe, trade_stats

ET = "America/New_York"

IS_EVAL_START = pd.Timestamp("2020-10-01", tz=ET)
IS_END = pd.Timestamp("2024-01-01", tz=ET)          # esclusivo
OOS_EVAL_START = pd.Timestamp("2024-01-01", tz=ET)
OOS_WARMUP_START = pd.Timestamp("2023-10-01", tz=ET)

EXITS = ["base", "final", "vwap"]
LOOKBACKS = [7, 14, 28]
INTERVALS = [15, 30, 60]
CONTROL = ("final", 14, 30)  # replica del paper

# tie-break: distanza dalla config del paper, componente per componente
def _paper_distance(v: tuple) -> tuple:
    exit_mode, lb, iv = v
    return (exit_mode != "final", abs(lb - 14), abs(iv - 30))


def run_variant(bars: pd.DataFrame, variant: tuple, eval_start: pd.Timestamp) -> dict:
    exit_mode, lookback, interval = variant
    res = run_backtest(
        bars,
        exit_mode=exit_mode,
        lookback=lookback,
        check_interval_min=interval,
        costs=CostModel(),
    )
    eq = res.equity[res.equity.index >= eval_start]
    rets = eq.pct_change().dropna()
    trades = res.trades[res.trades["entry_time"] >= eval_start] if not res.trades.empty else res.trades
    ts = trade_stats(trades)
    sr_daily = rets.mean() / rets.std() if rets.std() > 0 else np.nan
    years = len(rets) / TRADING_DAYS
    total = eq.iloc[-1] / eq.iloc[0] - 1
    return {
        "exit": exit_mode,
        "lookback": lookback,
        "interval": interval,
        "sharpe_ann": sr_daily * np.sqrt(TRADING_DAYS),
        "sr_daily": sr_daily,
        "cagr": (1 + total) ** (1 / years) - 1,
        "max_dd": (eq / eq.cummax() - 1).min(),
        "n_trades": ts.get("n_trades", 0),
        "win_rate": ts.get("win_rate", np.nan),
        "expectancy_bps": ts.get("expectancy_bps", np.nan),
        "returns": rets,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/spy_1min.parquet")
    p.add_argument("--out", default="reports/maroy_experiment.md")
    args = p.parse_args()

    rth = filter_rth(pd.read_parquet(args.data)).sort_index()
    is_bars = rth[rth.index < IS_END]
    oos_bars = rth[rth.index >= OOS_WARMUP_START]

    # --- fase 1: griglia in-sample ---
    rows = []
    for ex in EXITS:
        for lb in LOOKBACKS:
            for iv in INTERVALS:
                r = run_variant(is_bars, (ex, lb, iv), IS_EVAL_START)
                rows.append(r)
                print(f"IS {ex:>5}/{lb:>2}g/{iv:>2}m: Sharpe {r['sharpe_ann']:+.2f}  "
                      f"CAGR {r['cagr']:+.1%}  trades {r['n_trades']}")

    grid = pd.DataFrame(rows).drop(columns="returns")
    trial_srs = [r["sr_daily"] for r in rows]

    # --- fase 2: selezione meccanica ---
    best_sharpe = max(r["sharpe_ann"] for r in rows)
    candidates = [r for r in rows if r["sharpe_ann"] == best_sharpe]
    winner = min(candidates, key=lambda r: _paper_distance((r["exit"], r["lookback"], r["interval"])))
    wv = (winner["exit"], winner["lookback"], winner["interval"])
    print(f"\nVincente IS: {wv} (Sharpe {winner['sharpe_ann']:.2f})")

    # --- fase 3: deflated Sharpe ---
    dsr = deflated_sharpe(winner["returns"], trial_srs)
    print(f"DSR: {dsr['dsr']:.3f} (soglia SR0 daily {dsr['sr0_daily']:.4f}, "
          f"SR daily vincente {dsr['sr_daily']:.4f})")

    # --- fase 4: OOS, una sola volta, vincente + controllo ---
    oos_w = run_variant(oos_bars, wv, OOS_EVAL_START)
    oos_c = run_variant(oos_bars, CONTROL, OOS_EVAL_START)
    print(f"OOS vincente {wv}: Sharpe {oos_w['sharpe_ann']:+.2f}")
    print(f"OOS controllo {CONTROL}: Sharpe {oos_c['sharpe_ann']:+.2f}")

    # --- fase 5: verdetto ---
    c1 = dsr["dsr"] >= 0.95
    c2 = oos_w["sharpe_ann"] > oos_c["sharpe_ann"]
    c3 = oos_w["sharpe_ann"] > 0
    promoted = c1 and c2 and c3

    # --- report ---
    buf = io.StringIO()
    w = buf.write
    w("# Esperimento Maróy — risultati (protocollo commit 4d0a7cc)\n\n")
    w(f"Eseguito una sola volta il {pd.Timestamp.now(tz=ET).date()}. "
      "Selezione meccanica, nessuna variante aggiunta dopo il congelamento.\n\n")

    w("## Griglia in-sample completa (2020-10-01 → 2023-12-31)\n\n")
    g = grid.sort_values("sharpe_ann", ascending=False).reset_index(drop=True)
    g["sharpe_ann"] = g["sharpe_ann"].round(2)
    g["cagr"] = g["cagr"].map("{:+.1%}".format)
    g["max_dd"] = g["max_dd"].map("{:.1%}".format)
    g["win_rate"] = g["win_rate"].map("{:.1%}".format)
    g["expectancy_bps"] = g["expectancy_bps"].round(2)
    w(g.drop(columns="sr_daily").to_markdown(index=False) + "\n\n")

    w(f"## Vincente IS: `{wv[0]}` / lookback {wv[1]}g / check {wv[2]}min\n\n")
    w(f"- Sharpe IS: **{winner['sharpe_ann']:.2f}** (controllo IS: "
      f"{next(r['sharpe_ann'] for r in rows if (r['exit'], r['lookback'], r['interval']) == CONTROL):.2f})\n")
    w(f"- **Deflated Sharpe Ratio: {dsr['dsr']:.3f}** (N=27 trial; expected max "
      f"SR sotto H0: {dsr['sr0_daily'] * np.sqrt(TRADING_DAYS):.2f} annualizzato)\n")
    w(f"- C1 (DSR ≥ 0.95): **{'PASS' if c1 else 'FAIL'}**\n\n")

    w("## Out-of-sample (2024-01-01 → fine campione) — valutato una sola volta\n\n")
    tab = pd.DataFrame(
        {
            "Vincente": {
                "Sharpe": f"{oos_w['sharpe_ann']:.2f}",
                "CAGR": f"{oos_w['cagr']:+.1%}",
                "Max DD": f"{oos_w['max_dd']:.1%}",
                "Trades": oos_w["n_trades"],
                "Win rate": f"{oos_w['win_rate']:.1%}",
                "Expectancy (bps)": f"{oos_w['expectancy_bps']:+.2f}",
            },
            "Controllo (paper)": {
                "Sharpe": f"{oos_c['sharpe_ann']:.2f}",
                "CAGR": f"{oos_c['cagr']:+.1%}",
                "Max DD": f"{oos_c['max_dd']:.1%}",
                "Trades": oos_c["n_trades"],
                "Win rate": f"{oos_c['win_rate']:.1%}",
                "Expectancy (bps)": f"{oos_c['expectancy_bps']:+.2f}",
            },
        }
    )
    w(tab.to_markdown() + "\n\n")
    w(f"- C2 (Sharpe OOS vincente > controllo): **{'PASS' if c2 else 'FAIL'}**\n")
    w(f"- C3 (Sharpe OOS vincente > 0): **{'PASS' if c3 else 'FAIL'}**\n\n")

    w("## Verdetto\n\n")
    if promoted:
        w("**3/3 criteri superati: variante promossa**, in attesa di conferma "
          "sulla fase ES (dati CME, VWAP pieno) prima di qualsiasi uso.\n")
    else:
        w("**Criteri non superati: resta la configurazione del paper.** "
          "Come da protocollo, l'esperimento e' chiuso e non si riapre con "
          "nuove varianti su questi stessi dati.\n")
    w("\nDisclosure: vedi PROTOCOL_MAROY.md (OOS non vergine, feed IEX, "
      "campione corto).\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(buf.getvalue())
    print(f"\nReport scritto in {args.out}")


if __name__ == "__main__":
    main()
