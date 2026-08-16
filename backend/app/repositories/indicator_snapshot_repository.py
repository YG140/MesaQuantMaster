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

    def latest_for_symbol(
        self, symbol: str, now: datetime | None = None
    ) -> list[IndicatorSnapshot]:
        """Retorna o snapshot mais recente por indicador, mesmo se expirado.

        Usado apenas como ultimo recurso para preservar um valor stale com sua
        provenance (nunca como zero) quando nenhuma fonte mais atual resolveu
        o indicador. Nao deve ser usado para evitar a busca por dado atual —
        `valid_for_symbol` continua sendo a primeira tentativa.
        """
        rows = (
            self.db.query(IndicatorSnapshot)
            .filter(IndicatorSnapshot.symbol == symbol.upper().strip())
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
