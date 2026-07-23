from datetime import datetime, timedelta, timezone
import json

from sqlalchemy.orm import Session

from app.models.indicator_snapshot import IndicatorSnapshot
from app.schemas.market_intelligence import IndicatorStatus


class IndicatorSnapshotRepository:
    TTL_BY_LAYER_DAYS = {
        "market": 0,
        "fundamental": 95,
        "risk_liquidity": 1,
        "recommendation": 1,
    }

    def __init__(self, db: Session):
        self.db = db

    def save(self, symbol: str, asset_class: str, indicators: list) -> None:
        now = datetime.now(timezone.utc)
        for indicator in indicators:
            if indicator.status != IndicatorStatus.AVAILABLE or not hasattr(
                indicator.value, "as_tuple"
            ):
                continue
            layer = getattr(indicator.layer, "value", str(indicator.layer))
            days = self.TTL_BY_LAYER_DAYS.get(layer, 30)
            valid_until = now + (
                timedelta(minutes=2) if days == 0 else timedelta(days=days)
            )
            self.db.add(
                IndicatorSnapshot(
                    symbol=symbol,
                    asset_class=asset_class,
                    indicator_key=indicator.key,
                    value=indicator.value,
                    unit=indicator.unit,
                    period=indicator.period,
                    source=indicator.source,
                    source_type=getattr(indicator, "source_type", "provider"),
                    reference_date=indicator.reference_date,
                    collected_at=indicator.collected_at,
                    valid_until=valid_until,
                    provenance_json=json.dumps(
                        getattr(indicator, "provenance", {}),
                        ensure_ascii=False,
                        default=str,
                    ),
                )
            )
        self.db.commit()

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
