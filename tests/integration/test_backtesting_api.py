from __future__ import annotations

from decimal import Decimal


def as_decimal(value) -> Decimal:
    return Decimal(str(value))


def test_post_backtesting_run_returns_metrics(client):
    payload = {
        "initial_capital": "1000",
        "historical_data": [
            {"timestamp": "2026-01-01T10:00:00", "close": "10"},
            {"timestamp": "2026-01-02T10:00:00", "close": "12"},
            {"timestamp": "2026-01-03T10:00:00", "close": "15"},
        ],
        "signals": [
            {"timestamp": "2026-01-01T10:00:00", "signal": "BUY"},
            {"timestamp": "2026-01-03T10:00:00", "signal": "SELL"},
        ],
        "fee_percent": "0",
        "fixed_fee": "0",
    }

    response = client.post("/backtesting/run", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert as_decimal(data["final_equity"]) == Decimal("1500.00")
    assert data["trades_count"] == 1
    assert as_decimal(data["total_return_percent"]) == Decimal("50.00")
    assert as_decimal(data["benchmark_return_percent"]) == Decimal("50.00")
    assert as_decimal(data["excess_return_percent"]) == Decimal("0.00")
    assert len(data["equity_curve"]) == 3
    assert set(data["equity_curve"][0]) == {
        "timestamp",
        "cash",
        "position_value",
        "equity",
        "drawdown_percent",
    }
    assert data["trades"][0]["entry_price"] == "10"
    assert data["open_position"]["is_open"] is False
