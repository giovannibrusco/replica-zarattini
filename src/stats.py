"""Metriche di performance e tabelle di validazione.

Copre il piano di validazione della spec:
- metriche aggregate (total return, CAGR, vol, Sharpe, max drawdown)
- alfa/beta annualizzati vs benchmark (OLS su rendimenti giornalieri)
- statistiche trade-level: win rate, payoff ratio, expectancy,
  distribuzione perdite, losing streak massima
- tabella per anno
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def performance_summary(
    daily_returns: pd.Series, benchmark: pd.Series | None = None
) -> dict:
    r = daily_returns.dropna()
    n = len(r)
    if n == 0:
        return {}
    equity = (1 + r).cumprod()
    total_return = equity.iloc[-1] - 1
    years = n / TRADING_DAYS
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else np.nan
    ann_vol = r.std() * np.sqrt(TRADING_DAYS)
    sharpe = r.mean() / r.std() * np.sqrt(TRADING_DAYS) if r.std() > 0 else np.nan
    dd = equity / equity.cummax() - 1

    out = {
        "total_return": total_return,
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": dd.min(),
        "n_days": n,
    }

    if benchmark is not None:
        b = benchmark.reindex(r.index).dropna()
        rr = r.reindex(b.index)
        if len(b) > 2 and b.var() > 0:
            beta = rr.cov(b) / b.var()
            alpha_daily = rr.mean() - beta * b.mean()
            resid = rr - (alpha_daily + beta * b)
            se = resid.std() / np.sqrt(len(b))
            out["beta"] = beta
            out["alpha_ann"] = alpha_daily * TRADING_DAYS
            out["alpha_tstat"] = alpha_daily / se if se > 0 else np.nan
    return out


def trade_stats(trades: pd.DataFrame, unit_multiplier: float = 1.0) -> dict:
    """unit_multiplier: 1 per azioni, 50 per ES, 5 per MES (serve per il
    notional corretto nell'expectancy in bps)."""
    if trades.empty:
        return {"n_trades": 0}
    pnl = trades["net_pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    win_rate = len(wins) / len(pnl)
    avg_win = wins.mean() if len(wins) else np.nan
    avg_loss = losses.mean() if len(losses) else np.nan
    payoff = avg_win / abs(avg_loss) if len(losses) and avg_loss != 0 else np.nan

    # rendimento per trade in bps del notional scambiato (confronto Quantitativo)
    notional = trades["units"] * trades["entry_px"] * unit_multiplier
    ret_bps = (pnl / notional * 1e4).mean()

    # losing streak massima
    is_loss = (pnl <= 0).to_numpy()
    streak = max_streak = 0
    for x in is_loss:
        streak = streak + 1 if x else 0
        max_streak = max(max_streak, streak)

    return {
        "n_trades": len(pnl),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff,
        "expectancy": pnl.mean(),
        "expectancy_bps": ret_bps,
        "worst_trade": pnl.min(),
        "loss_p95": losses.quantile(0.05) if len(losses) else np.nan,
        "max_losing_streak": max_streak,
    }


def yearly_table(
    daily_returns: pd.Series, benchmark: pd.Series | None = None
) -> pd.DataFrame:
    """Metriche per anno solare (validazione robustezza temporale)."""
    rows = {}
    for year, r in daily_returns.groupby(daily_returns.index.year):
        b = benchmark[benchmark.index.year == year] if benchmark is not None else None
        rows[year] = performance_summary(r, b)
    return pd.DataFrame(rows).T


def regime_table(daily_returns: pd.Series, vix_close: pd.Series) -> pd.DataFrame:
    """Metriche per regime VIX (livello di chiusura del giorno precedente)."""
    vix = vix_close.reindex(daily_returns.index).ffill().shift(1)
    bins = [0, 15, 20, 30, 40, np.inf]
    labels = ["<15", "15-20", "20-30", "30-40", ">40"]
    regime = pd.cut(vix, bins=bins, labels=labels)
    rows = {}
    for reg, r in daily_returns.groupby(regime, observed=True):
        rows[str(reg)] = performance_summary(r)
    return pd.DataFrame(rows).T


def deflated_sharpe(
    daily_returns: pd.Series,
    trial_sharpes_daily: "list[float] | np.ndarray",
) -> dict:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).

    Probabilita' che lo Sharpe osservato del vincente superi l'expected max
    Sharpe di N trial sotto l'ipotesi nulla (nessuna skill), con correzione
    per skew e curtosi dei rendimenti. Tutto in unita' giornaliere.

    trial_sharpes_daily: Sharpe giornalieri (non annualizzati) di TUTTI i
    trial eseguiti, incluso il vincente.
    """
    from scipy.stats import norm

    r = daily_returns.dropna()
    t_len = len(r)
    sr = r.mean() / r.std()  # Sharpe giornaliero osservato
    skew = r.skew()
    kurt = r.kurt() + 3.0  # da eccesso a curtosi "raw"

    trials = np.asarray(trial_sharpes_daily, dtype=float)
    n = len(trials)
    var_sr = trials.var(ddof=1)

    gamma = 0.5772156649015329  # Eulero-Mascheroni
    e = np.e
    # expected max SR sotto H0 (SR veri tutti nulli)
    sr0 = np.sqrt(var_sr) * (
        (1 - gamma) * norm.ppf(1 - 1 / n) + gamma * norm.ppf(1 - 1 / (n * e))
    )
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)
    z = (sr - sr0) * np.sqrt(t_len - 1) / denom
    return {
        "sr_daily": sr,
        "sr0_daily": float(sr0),
        "dsr": float(norm.cdf(z)),
        "n_trials": n,
        "t_obs": t_len,
    }


def format_summary(perf: dict, tstats: dict | None = None) -> str:
    lines = []
    fmt = {
        "total_return": ("Total return", "{:+.1%}"),
        "cagr": ("CAGR", "{:+.2%}"),
        "ann_vol": ("Vol annualizzata", "{:.2%}"),
        "sharpe": ("Sharpe", "{:.2f}"),
        "max_drawdown": ("Max drawdown", "{:.1%}"),
        "alpha_ann": ("Alfa annualizzato", "{:+.2%}"),
        "alpha_tstat": ("t-stat alfa", "{:.2f}"),
        "beta": ("Beta", "{:.2f}"),
        "n_days": ("Giorni", "{:d}"),
    }
    for key, (label, f) in fmt.items():
        if key in perf and pd.notna(perf[key]):
            lines.append(f"{label:>20}: {f.format(perf[key])}")
    if tstats:
        tfmt = {
            "n_trades": ("Trades", "{:d}"),
            "win_rate": ("Win rate", "{:.1%}"),
            "payoff_ratio": ("Payoff ratio", "{:.2f}"),
            "expectancy": ("Expectancy ($)", "{:+.2f}"),
            "expectancy_bps": ("Expectancy (bps)", "{:+.2f}"),
            "max_losing_streak": ("Max losing streak", "{:d}"),
        }
        for key, (label, f) in tfmt.items():
            if key in tstats and pd.notna(tstats[key]):
                lines.append(f"{label:>20}: {f.format(tstats[key])}")
    return "\n".join(lines)
