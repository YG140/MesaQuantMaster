import json

from sqlalchemy.orm import Session

from app.models.indicator_snapshot import IndicatorSnapshot
from app.schemas.market_sync import MarketSyncSnapshot


class MarketSyncRepository:
    """Persiste um lote sem commit; a transação pertence ao chamador."""

    def __init__(self, db: Session):
        self.db = db

    def upsert_batch(self, snapshots: list[MarketSyncSnapshot]) -> int:
        written = 0
        with self.db.begin_nested():
            for item in snapshots:
                row = (
                    self.db.query(IndicatorSnapshot)
                    .filter(
                        IndicatorSnapshot.symbol == item.symbol,
                        IndicatorSnapshot.indicator_key == item.indicator_key,
                        IndicatorSnapshot.source == item.provider,
                        IndicatorSnapshot.source_type == item.source_type,
                    )
                    .order_by(IndicatorSnapshot.collected_at.desc())
                    .first()
                )
                if row is None:
                    row = IndicatorSnapshot(
                        symbol=item.symbol,
                        asset_class=item.asset_class,
                        indicator_key=item.indicator_key,
                    )
                    self.db.add(row)
                row.value = item.value
                row.unit = item.unit
                row.period = "current"
                row.source = item.provider
                row.source_type = item.source_type
                row.reference_date = item.reference_date
                row.collected_at = item.collected_at
                row.valid_until = item.valid_until
                row.provenance_json = json.dumps(
                    {
                        "provider": item.provider,
                        "source_type": item.source_type,
                        "currency_code": item.currency_code,
                        "reference_date": item.reference_date.isoformat(),
                        "collected_at": item.collected_at.isoformat(),
                        "valid_until": item.valid_until.isoformat(),
                    }
                )
                written += 1
            self.db.flush()
        return written
