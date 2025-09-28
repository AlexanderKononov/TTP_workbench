# utils/perf.py
import numpy as np

def performance_metrics(portfolio_series, trading_days_per_year=252, risk_free_rate=0.0):
    # portfolio_series is daily total equity indexed by date
    returns = portfolio_series.pct_change().dropna()
    total_return = portfolio_series.iloc[-1] / portfolio_series.iloc[0] - 1

    # CAGR
    n_days = len(returns)
    years = n_days / trading_days_per_year if trading_days_per_year else None
    cagr = (portfolio_series.iloc[-1] / portfolio_series.iloc[0]) ** (1/years) - 1 if years and years > 0 else None

    # drawdowns
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    # Sharpe (annualized)
    ann_mean = returns.mean() * trading_days_per_year
    ann_std = returns.std() * (trading_days_per_year ** 0.5)
    sharpe = (ann_mean - risk_free_rate) / ann_std if ann_std != 0 else np.nan

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe
    }
