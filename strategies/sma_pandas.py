# strategies/sma_pandas.py
import pandas as pd

def generate_sma_signals(df: pd.DataFrame, short: int = 20, long: int = 50) -> pd.DataFrame:
    df = df.copy()
    df["sma_short"] = df["Close"].rolling(short).mean()
    df["sma_long"] = df["Close"].rolling(long).mean()
    # signal: 1 when short > long else 0
    df["signal"] = 0
    df.loc[df["sma_short"] > df["sma_long"], "signal"] = 1
    # trades are changes in signal
    df["trade"] = df["signal"].diff().fillna(0)  # +1 buy, -1 sell
    return df

def simple_backtest(df: pd.DataFrame, initial_cash: float = 10000, risk_fraction: float = 0.1):
    df = generate_sma_signals(df)
    cash = initial_cash
    position = 0
    portfolio_values = []

    for dt, row in df.iterrows():
        price = row["Close"]
        action = row["trade"]
        # BUY
        if action == 1:
            # allocate risk_fraction of current cash
            allocate = cash * risk_fraction
            qty = int(allocate // price)
            if qty > 0:
                cost = qty * price
                cash -= cost
                position += qty
        # SELL (flatten position)
        elif action == -1 and position > 0:
            proceeds = position * price
            cash += proceeds
            position = 0
        # record portfolio value each day
        pv = cash + position * price
        portfolio_values.append({"date": dt, "portfolio_value": pv})

    port_df = pd.DataFrame(portfolio_values).set_index("date")
    return port_df, df  # returns daily portfolio curve and df with signals
