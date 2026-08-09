"""FIFO matching of Format A (fills) into Format-B-equivalent closed trades.

BUILD_PLAN.md §2 flagged this as a "v2 (stretch)" feature: fills are
individual order executions and aren't directly usable for trade-level PnL
- a symbol's fills must be netted, in execution order, into round-trip
trades before statistics.compute_stats() can run on them.

Algorithm, per (market, symbol) group, fills sorted by fill_time:

- Fills on the same side as the currently open position extend it (added to
  a FIFO queue of open lots).
- A fill on the opposite side closes against the oldest open lots first
  (FIFO). If it exactly (or more than) exhausts the queue, the round-trip
  trade is complete as of that fill's timestamp; any quantity left over
  after the queue empties immediately opens a new trade in the reversed
  direction (a single fill can both close one trade and open the next).
- Fees are prorated per unit within each fill and summed across both sides
  of the matched quantity, so a fill that gets split across multiple trades
  contributes fee proportional to the quantity used in each.

profit is the gross price P&L (sum of sell fill value matched into the trade
minus sum of buy fill value matched into it) - this formula is sign-correct
for both long (buy-to-open) and short (sell-to-open) trades without needing
a side-dependent branch, since it's just net cash flow. fee is total fees
prorated into the trade; net_pnl = profit - fee, matching the convention
statistics.compute_stats() already assumes.

Any position still open at the end of a symbol's fills (never returned to
zero net quantity within the uploaded file) can't be assigned a realized
PnL and is excluded from the trades result; it's reported separately so the
caller can warn the user instead of silently dropping data.
"""
from __future__ import annotations

from collections import deque

import pandas as pd

EPS = 1e-9


def match_fills_to_trades(fills: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match fills into closed round-trip trades via per-symbol FIFO netting.

    Expects the schema produced by src.parsing.normalize_fills: fill_time,
    market, symbol, direction, price, quantity, total, fee.

    Returns (trades, open_positions):
    - trades: trade_time, market, symbol, direction, profit, profit_pct,
      fee, net_pnl, entry_time, quantity - compatible with
      statistics.compute_stats() (profit_pct is always NA; fills don't carry
      a return-% baseline).
    - open_positions: market, symbol, direction, quantity, avg_price,
      opened_at - one row per symbol left with an unclosed position, i.e.
      fills that never netted back to zero within this file.
    """
    trades: list[dict] = []
    open_positions: list[dict] = []

    for (market, symbol), group in fills.groupby(["market", "symbol"], sort=False):
        group = group.sort_values("fill_time", kind="stable")

        open_lots: deque[dict] = deque()
        position_side = 0  # +1 while net long, -1 while net short, 0 flat
        direction = None
        entry_time = None
        buy_value = 0.0
        sell_value = 0.0
        fee_total = 0.0
        opened_qty = 0.0  # total size opened during the current round trip

        def _open(side: int, side_label: str, price: float, qty: float, fee: float, time) -> None:
            # fee_total is intentionally left untouched here: opening-side
            # fee is only realized (added to fee_total) once the matching
            # portion of the position actually closes, in the while-loop
            # below - this avoids double-counting it once at open time and
            # again, prorated, at close time. A lot that never closes (an
            # unresolved open position) correctly never contributes its fee
            # to any finalized trade.
            nonlocal position_side, direction, entry_time, buy_value, sell_value, opened_qty
            position_side = side
            direction = side_label
            entry_time = time
            open_lots.append({"qty": qty, "price": price, "fee_per_unit": fee / qty if qty else 0.0})
            buy_value = price * qty if side_label == "buy" else 0.0
            sell_value = price * qty if side_label == "sell" else 0.0
            opened_qty = qty

        for fill in group.itertuples(index=False):
            side_label = str(fill.direction).lower()
            side = 1 if side_label == "buy" else -1
            price = float(fill.price)
            qty = float(fill.quantity)
            fee = float(fill.fee)
            if qty <= EPS:
                continue

            if position_side == 0:
                _open(side, side_label, price, qty, fee, fill.fill_time)
                continue

            if side == position_side:
                open_lots.append({"qty": qty, "price": price, "fee_per_unit": fee / qty})
                if side_label == "buy":
                    buy_value += price * qty
                else:
                    sell_value += price * qty
                opened_qty += qty
                continue

            # Opposite side: close against the oldest open lots first.
            remaining = qty
            closing_fee_per_unit = fee / qty
            while remaining > EPS and open_lots:
                lot = open_lots[0]
                matched = min(lot["qty"], remaining)
                if side_label == "buy":
                    buy_value += price * matched
                else:
                    sell_value += price * matched
                # Both sides of the matched slice contribute fee: the
                # opening lot's own fee and this closing fill's fee.
                fee_total += (lot["fee_per_unit"] + closing_fee_per_unit) * matched
                lot["qty"] -= matched
                remaining -= matched
                if lot["qty"] <= EPS:
                    open_lots.popleft()

            if not open_lots:
                profit = sell_value - buy_value
                trades.append(
                    {
                        "trade_time": fill.fill_time,
                        "market": market,
                        "symbol": symbol,
                        "direction": direction,
                        "profit": profit,
                        "profit_pct": pd.NA,
                        "fee": fee_total,
                        "net_pnl": profit - fee_total,
                        "entry_time": entry_time,
                        "quantity": opened_qty,
                    }
                )
                position_side = 0
                direction = None
                entry_time = None
                buy_value = sell_value = fee_total = 0.0
                opened_qty = 0.0

                if remaining > EPS:
                    # This fill both closed the prior trade and opened a new
                    # (reversed) one with its own leftover quantity.
                    matched_fee = fee * (remaining / qty)
                    _open(side, side_label, price, remaining, matched_fee, fill.fill_time)
            # else: position reduced but not closed yet - keep accumulating.

        if open_lots:
            leftover_qty = sum(lot["qty"] for lot in open_lots)
            leftover_value = sum(lot["qty"] * lot["price"] for lot in open_lots)
            open_positions.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "direction": direction,
                    "quantity": leftover_qty,
                    "avg_price": leftover_value / leftover_qty if leftover_qty else 0.0,
                    "opened_at": entry_time,
                }
            )

    trades_df = pd.DataFrame(
        trades,
        columns=[
            "trade_time",
            "market",
            "symbol",
            "direction",
            "profit",
            "profit_pct",
            "fee",
            "net_pnl",
            "entry_time",
            "quantity",
        ],
    )
    if not trades_df.empty:
        trades_df = trades_df.sort_values("trade_time").reset_index(drop=True)

    open_positions_df = pd.DataFrame(
        open_positions,
        columns=["market", "symbol", "direction", "quantity", "avg_price", "opened_at"],
    )
    return trades_df, open_positions_df
