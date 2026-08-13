from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.indicator_snapshot import IndicatorSnapshot


class IndicatorSnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def history(self, symbol: str) -> list[IndicatorSnapshot]:
        return (
            self.db.query(IndicatorSnapshot)
            .filter(IndicatorSnapshot.symbol == symbol.upper())
            .order_by(IndicatorSnapshot.collected_at.desc())
            .all()
        )

    def valid_for_symbol(
        self, symbol: str, now: datetime | None = None
    ) -> list[IndicatorSnapshot]:
        reference = now or datetime.now(timezone.utc)
        rows = (
            self.db.query(IndicatorSnapshot)
            .filter(
                IndicatorSnapshot.symbol == symbol.upper().strip(),
                IndicatorSnapshot.valid_until > reference,
            )
            .order_by(
                IndicatorSnapshot.indicator_key,
                IndicatorSnapshot.collected_at.desc(),
            )
            .all()
        )
        latest = {}
        for row in rows:
            latest.setdefault(row.indicator_key, row)
        return list(latest.values())
