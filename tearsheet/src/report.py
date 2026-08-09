"""Shared Streamlit rendering for a single session's trade report.

Used by both the Upload page (freshly processed file) and the Session
Details page (a previously stored session) so the KPI/chart/table layout
only exists in one place.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.statistics import equity_curve
from src.visualisation import (
    drawdown_chart,
    equity_curve_chart,
    pnl_by_symbol_chart,
    pnl_histogram,
)


def render_trade_report(trades: pd.DataFrame, stats: dict) -> None:
    st.subheader("Session Results")

    row1 = st.columns(4)
    row1[0].metric("Net PnL", f"{stats['net_pnl']:.2f}")
    row1[1].metric("Trades", stats["trade_count"])
    row1[2].metric("Win Rate", f"{stats['win_rate']*100:.1f}%")
    row1[3].metric("Max Drawdown", f"{stats['max_drawdown']:.2f}")

    row2 = st.columns(4)
    row2[0].metric("Mean PnL / Trade", f"{stats['mean_pnl']:.2f}")
    row2[1].metric(
        "Profit Factor",
        f"{stats['profit_factor']:.2f}" if stats["profit_factor"] != float("inf") else "∞",
    )
    row2[2].metric("Gross PnL", f"{stats['gross_pnl']:.2f}")
    row2[3].metric("Total Fees", f"{stats['total_fees']:.2f}")

    row3 = st.columns(4)
    row3[0].metric("Avg Win", f"{stats['avg_win']:.2f}")
    row3[1].metric("Avg Loss", f"{stats['avg_loss']:.2f}")
    row3[2].metric("Largest Win", f"{stats['largest_win']:.2f}")
    row3[3].metric("Largest Loss", f"{stats['largest_loss']:.2f}")

    if stats["low_sample_size"]:
        st.caption(
            f"⚠ Only {stats['trade_count']} trades in this sample — statistics "
            "(especially Sharpe/expectancy) are noisy at this size."
        )

    st.divider()

    curve = equity_curve(trades)
    chart_col1, chart_col2 = st.columns(2)
    chart_col1.plotly_chart(equity_curve_chart(curve), use_container_width=True)
    chart_col2.plotly_chart(drawdown_chart(curve), use_container_width=True)

    chart_col3, chart_col4 = st.columns(2)
    chart_col3.plotly_chart(pnl_histogram(trades), use_container_width=True)
    chart_col4.plotly_chart(pnl_by_symbol_chart(trades), use_container_width=True)

    st.divider()

    st.subheader("Trades")
    st.dataframe(trades, use_container_width=True)

    st.download_button(
        "Download processed trades (CSV)",
        data=trades.to_csv(index=False).encode("utf-8"),
        file_name="processed_trades.csv",
        mime="text/csv",
    )
