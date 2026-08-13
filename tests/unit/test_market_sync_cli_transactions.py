from argparse import Namespace

import pytest

from app.cli import market_sync
from app.schemas.market_sync import MarketSyncReport


class SessionSpy:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def cli_args(backup, *, apply=True):
    return Namespace(
        tickers=["PETR4", "VALE3"],
        max_assets=2,
        max_calls=1,
        timeout=10,
        offline=True,
        apply=apply,
        confirm_apply=apply,
        expected_database=":memory:" if apply else None,
        backup=str(backup) if apply else None,
    )


def report():
    return MarketSyncReport(
        dry_run=False,
        requested=2,
        processed=2,
        calls_used=0,
        snapshots_ready=2,
        snapshots_written=2,
    )


def test_cli_apply_commits_once_for_the_whole_batch(tmp_path, monkeypatch, capsys):
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"test backup")
    session = SessionSpy()

    class FakeService:
        def __init__(self, **_kwargs):
            pass

        def run(self, _request, *, apply=False):
            assert apply is True
            return report()

    monkeypatch.setattr(market_sync, "SessionLocal", lambda: session)
    monkeypatch.setattr(market_sync, "MarketSyncService", FakeService)
    monkeypatch.setattr(
        market_sync,
        "parser",
        lambda: type("P", (), {"parse_args": lambda _self: cli_args(backup)})(),
    )

    market_sync.main()

    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.closed == 1
    assert '"snapshots_written": 2' in capsys.readouterr().out


def test_cli_apply_rolls_back_once_on_batch_failure(tmp_path, monkeypatch):
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"test backup")
    session = SessionSpy()

    class FailingService:
        def __init__(self, **_kwargs):
            pass

        def run(self, _request, *, apply=False):
            raise RuntimeError("controlled batch failure")

    monkeypatch.setattr(market_sync, "SessionLocal", lambda: session)
    monkeypatch.setattr(market_sync, "MarketSyncService", FailingService)
    monkeypatch.setattr(
        market_sync,
        "parser",
        lambda: type("P", (), {"parse_args": lambda _self: cli_args(backup)})(),
    )

    with pytest.raises(RuntimeError, match="controlled batch failure"):
        market_sync.main()

    assert session.commits == 0
    assert session.rollbacks == 1
    assert session.closed == 1
