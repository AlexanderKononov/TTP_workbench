import pandas as pd
import pytest

from src.statistics import compute_stats, equity_curve

# Hand-computed fixture: 4 trades, net_pnl = profit - fee
# t1: +10 - 1 = 9   (win)
# t2: -6  - 1 = -7  (loss)
# t3: +4  - 1 = 3   (win)
# t4: -2  - 1 = -3  (loss)
# cumulative: 9, 2, 5, 2  -> running max: 9, 9, 9, 9 -> drawdown: 0, 7, 4, 7 -> max_drawdown = 7
FIXTURE = pd.DataFrame(
    {
        "trade_time": pd.to_datetime(
            ["2026-01-01 10:00", "2026-01-01 11:00", "2026-01-01 12:00", "2026-01-01 13:00"]
        ),
        "market": ["X"] * 4,
        "symbol": ["AAA", "AAA", "BBB", "BBB"],
        "direction": ["sell", "sell", "buy", "buy"],
        "profit": [10.0, -6.0, 4.0, -2.0],
        "profit_pct": [1.0, -1.0, 1.0, -1.0],
        "fee": [1.0, 1.0, 1.0, 1.0],
    }
)
FIXTURE["net_pnl"] = FIXTURE["profit"] - FIXTURE["fee"]


def test_compute_stats_known_values():
    stats = compute_stats(FIXTURE)
    assert stats["trade_count"] == 4
    assert stats["gross_pnl"] == pytest.approx(6.0)
    assert stats["total_fees"] == pytest.approx(4.0)
    assert stats["net_pnl"] == pytest.approx(2.0)
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["mean_pnl"] == pytest.approx(0.5)
    assert stats["avg_win"] == pytest.approx(6.0)  # (9 + 3) / 2
    assert stats["avg_loss"] == pytest.approx(-5.0)  # (-7 + -3) / 2
    assert stats["largest_win"] == pytest.approx(9.0)
    assert stats["largest_loss"] == pytest.approx(-7.0)
    assert stats["profit_factor"] == pytest.approx(12 / 10)  # sum(wins)=12, sum(losses)=-10
    assert stats["max_drawdown"] == pytest.approx(7.0)
    assert stats["low_sample_size"] is True


def test_profit_factor_infinite_with_no_losses():
    only_wins = FIXTURE[FIXTURE["net_pnl"] > 0]
    stats = compute_stats(only_wins)
    assert stats["profit_factor"] == float("inf")


def test_compute_stats_empty_raises():
    with pytest.raises(ValueError):
        compute_stats(FIXTURE.iloc[0:0])


def test_equity_curve_shape_and_drawdown():
    curve = equity_curve(FIXTURE)
    assert list(curve["cumulative_pnl"]) == pytest.approx([9.0, 2.0, 5.0, 2.0])
    assert list(curve["drawdown"]) == pytest.approx([0.0, -7.0, -4.0, -7.0])
