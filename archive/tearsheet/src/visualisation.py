"""Plotly chart builders for the tearsheet app."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

POSITIVE_COLOR = "#2E7D32"
NEGATIVE_COLOR = "#C62828"
LINE_COLOR = "#1565C0"
UPLOAD_MARKER_COLOR = "#EB6834"


def equity_curve_chart(curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve["trade_time"],
            y=curve["cumulative_pnl"],
            mode="lines",
            name="Cumulative Net PnL",
            line=dict(color=LINE_COLOR, width=2),
        )
    )
    fig.update_layout(
        title="Equity Curve (Cumulative Net PnL)",
        xaxis_title="Time",
        yaxis_title="Cumulative PnL",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def drawdown_chart(curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve["trade_time"],
            y=curve["drawdown"],
            mode="lines",
            name="Drawdown",
            line=dict(color=NEGATIVE_COLOR, width=2),
            fill="tozeroy",
        )
    )
    fig.update_layout(
        title="Drawdown",
        xaxis_title="Time",
        yaxis_title="Drawdown",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def pnl_histogram(trades: pd.DataFrame) -> go.Figure:
    colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in trades["net_pnl"]]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=trades["trade_time"],
            y=trades["net_pnl"],
            marker_color=colors,
            name="Net PnL per Trade",
        )
    )
    fig.update_layout(
        title="Net PnL per Trade",
        xaxis_title="Time",
        yaxis_title="Net PnL",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def activity_timeline_chart(daily: pd.DataFrame) -> go.Figure:
    """Trades-per-day bars with upload-day markers on the same timeline.

    One axis, two traces: the bar height is trade frequency (sequential,
    single hue); the diamond row is a status overlay (an upload happened
    that day), held at a fixed height above the bars rather than glued to
    each bar's top, so upload cadence reads independently of trade volume.
    """
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=daily["date"],
            y=daily["trade_count"],
            name="Trades",
            marker_color=LINE_COLOR,
            hovertemplate="%{x|%b %d, %Y}<br>%{y} trade(s)<extra></extra>",
        )
    )

    uploads = daily[daily["uploaded"]]
    if not uploads.empty:
        marker_y = max(daily["trade_count"].max(), 1) * 1.15
        fig.add_trace(
            go.Scatter(
                x=uploads["date"],
                y=[marker_y] * len(uploads),
                mode="markers",
                name="Upload",
                marker=dict(symbol="diamond", size=10, color=UPLOAD_MARKER_COLOR, line=dict(width=1, color="white")),
                customdata=[
                    (", ".join(files) if files else "", count)
                    for files, count in zip(uploads["uploaded_files"], uploads["upload_count"])
                ],
                hovertemplate="%{x|%b %d, %Y}<br>Uploaded: %{customdata[0]}<extra></extra>",
            )
        )

    fig.update_layout(
        title="Trading Activity",
        xaxis_title="Date",
        yaxis_title="Trades per day",
        bargap=0.2,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="closest",
    )
    return fig


def pnl_by_symbol_chart(trades: pd.DataFrame) -> go.Figure:
    by_symbol = trades.groupby("symbol")["net_pnl"].sum().sort_values()
    colors = [POSITIVE_COLOR if v >= 0 else NEGATIVE_COLOR for v in by_symbol.values]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=by_symbol.values,
            y=by_symbol.index,
            orientation="h",
            marker_color=colors,
        )
    )
    fig.update_layout(
        title="Net PnL by Symbol",
        xaxis_title="Net PnL",
        margin=dict(l=100, r=20, t=50, b=40),
    )
    return fig
