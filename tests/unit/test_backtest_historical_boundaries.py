"""Edge cases rejected before a historical simulation may claim a period return.

The comparison window must be the same for securities and the benchmark.
Fixtures are synthetic, never live investment returns.
"""
from datetime import timedelta
import pytest

from test_portfolio_walk_forward_engine import D1, D2, period, run


def test_security_start_index_outside_decision_window_is_rejected():
    p = period()
    p.realized_returns[0].start_observed_at = D1 - timedelta(days=30)
    with pytest.raises(ValueError, match="(inicial|janela|decisão)"):
        run([p])


def test_security_end_index_from_future_week_is_rejected():
    p = period()
    p.realized_returns[0].end_observed_at = D2 + timedelta(days=7)
    with pytest.raises(ValueError, match="(final|avaliação|janela)"):
        run([p])


def test_benchmark_end_index_from_later_window_is_rejected():
    p = period()
    p.benchmark.end_observed_at = D2 + timedelta(days=8)
    with pytest.raises(ValueError, match="(Benchmark|benchmark|avaliação|janela)"):
        run([p])


def test_benchmark_start_index_far_before_decision_is_rejected():
    p = period()
    p.benchmark.start_observed_at = D1 - timedelta(days=40)
    with pytest.raises(ValueError, match="(benchmark|Benchmark|inicial|decisão|janela)"):
        run([p])
