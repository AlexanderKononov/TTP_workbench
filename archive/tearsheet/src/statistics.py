"""Pure, testable statistics calculations over a normalized trades DataFrame.

Expects the schema produced by src.parsing.normalize_trades:
trade_time, market, symbol, direction, profit, profit_pct, fee, net_pnl.
"""
from __future__ import annotations

import pandas as pd


def compute_stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        raise ValueError("Cannot compute statistics on an empty trades table.")

    trades = trades.sort_values("trade_time")
    net = trades["net_pnl"]

    wins = net[net > 0]
    losses = net[net < 0]

    trade_count = len(trades)
    win_rate = len(wins) / trade_count

    gross_pnl = float(trades["profit"].sum())
    total_fees = float(trades["fee"].sum())
    net_pnl = float(net.sum())

    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0

    sum_wins = float(wins.sum())
    sum_losses = float(losses.sum())
    profit_factor = (sum_wins / abs(sum_losses)) if sum_losses != 0 else float("inf")

    cumulative = net.cumsum()
    running_max = cumulative.cummax()
    drawdown_series = running_max - cumulative
    max_drawdown = float(drawdown_series.max())

    expectancy = win_rate * avg_win - (1 - win_rate) * abs(avg_loss)

    std = net.std()
    sharpe = float(net.mean() / std) if std and not pd.isna(std) and std != 0 else None

    return {
        "trade_count": trade_count,
        "gross_pnl": gross_pnl,
        "total_fees": total_fees,
        "net_pnl": net_pnl,
        "win_rate": win_rate,
        "mean_pnl": float(net.mean()),
        "median_pnl": float(net.median()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": float(net.max()),
        "largest_loss": float(net.min()),
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "expectancy": expectancy,
        "sharpe": sharpe,
        "low_sample_size": trade_count < 30,
    }


def equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    """Cumulative net PnL over time, plus running drawdown, for charting."""
    trades = trades.sort_values("trade_time").reset_index(drop=True)
    curve = pd.DataFrame()
    curve["trade_time"] = trades["trade_time"]
    curve["cumulative_pnl"] = trades["net_pnl"].cumsum()
    running_max = curve["cumulative_pnl"].cummax()
    curve["drawdown"] = curve["cumulative_pnl"] - running_max
    return curve
