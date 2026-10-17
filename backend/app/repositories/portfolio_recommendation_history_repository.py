"""Append-only storage for reproducible portfolio recommendations.

The SHA-256 detects accidental later changes to the stored JSON; it does
NOT prove independent timestamping, data provenance, or market performance.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.portfolio_recommendation_run import PortfolioRecommendationRun
from app.models.portfolio_policy import PortfolioPolicy
from app.schemas.intelligence import BuildPortfolioRequest, BuildPortfolioResponse

ENGINE_VERSION = "smart_portfolio_engine-v1"
MAX_RECORD_BYTES = 2 * 1024 * 1024


def canonical_record(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def policy_snapshot(policy: PortfolioPolicy | None) -> dict | None:
    if policy is None:
        return None
    return {
        "objective": policy.objective,
        "risk_profile": policy.risk_profile,
        "investment_horizon": policy.investment_horizon,
        "monthly_contribution": str(policy.monthly_contribution),
        "maximum_weight_per_asset": str(policy.maximum_weight_per_asset),
        "maximum_weight_per_sector": str(policy.maximum_weight_per_sector),
        "maximum_weight_per_issuer": str(policy.maximum_weight_per_issuer),
        "rebalance_tolerance": str(policy.rebalance_tolerance),
        "allocations": [
            {
                "asset_class": item.asset_class,
                "target_percentage": str(item.target_percentage),
                "minimum_percentage": str(item.minimum_percentage),
                "maximum_percentage": str(item.maximum_percentage),
                "enabled": item.enabled,
            }
            for item in sorted(policy.allocations, key=lambda x: x.asset_class)
        ],
    }


def recommendation_record(
    request: BuildPortfolioRequest,
    result: BuildPortfolioResponse,
    policy: PortfolioPolicy | None = None,
) -> dict:
    """Copy real, dated recommendation evidence, not forecasts or personal questionnaires."""
    return {
        "schema_version": 1,
        "engine_version": ENGINE_VERSION,
        "generated_at": result.generated_at.isoformat(),
        "status": result.status,
        "confidence": result.confidence,
        "request": {
            "available_amount": str(request.available_amount),
            "objective": request.objective,
            "horizon": request.horizon,
            "risk_profile": request.risk_profile,
            "max_assets": request.max_assets,
            "allowed_classes": request.allowed_classes,
            "prohibited_classes": request.prohibited_classes,
        },
        "strategy": {
            "policy_id": str(result.policy_id) if result.policy_id else None,
            "policy_source": result.policy_source,
            "policy_snapshot": policy_snapshot(policy),
        },
        "universe": {
            "total": result.preflight.universe_total,
            "considered": result.preflight.universe_considered,
            "truncated": result.preflight.universe_truncated,
            "errors": result.preflight.provider_error_count,
            "eligible": result.preflight.eligible_count,
            "excluded": result.preflight.excluded_count,
            "source_failures": result.preflight.provider_failure_reason_counts,
        },
        "portfolio_context": {
            "existing_positions_count": result.existing_positions_count,
            "existing_portfolio_value": str(result.existing_portfolio_value),
        },
        "allocations": [
            row.model_dump(mode="json") for row in result.class_allocations
        ],
        "assets": [
            asset.model_dump(mode="json", include={
                "symbol", "name", "asset_class", "sector", "issuer",
                "recommended_percentage", "recommended_amount",
                "score", "reasons", "risks", "indicators_used",
                "missing_data", "confidence", "reference_price",
                "quote_observed_at", "executable_quantity", "executable_amount",
                "effective_percentage", "valuation_status", "valuation_confidence",
                "valuation_methods", "estimated_range_low", "estimated_range_high",
                "peer_comparison", "trading_symbol", "economic_identity",
                "execution_impediments",
            })
            for asset in result.assets
        ],
        "exclusions": [row.model_dump(mode="json") for row in result.exclusions],
        "totals": {
            "allocated": str(result.total_allocated_amount),
            "unallocated": str(result.unallocated_amount),
        },
        "validation_status": "recommendation_record_only",
        "limitations": [
            "Registro da decisão real, não evidência de rentabilidade futura.",
            "Hash detecta alterações no registro; não certifica fontes nem hora externa.",
            "Sem cotações posteriores auditadas ou backtest walk-forward validado.",
        ],
    }


class PortfolioRecommendationHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, user_id: UUID, request: BuildPortfolioRequest,
             result: BuildPortfolioResponse) -> PortfolioRecommendationRun:
        # Policy actually persisted for authenticated user: never accept user_id
        # or policy from a request body. Capture effective profile at this moment.
        policy = (
            self.db.query(PortfolioPolicy)
            .filter(PortfolioPolicy.user_id == user_id)
            .first()
        )
        record = recommendation_record(request, result, policy)
        serialized = canonical_record(record)
        if len(serialized.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError("Registro da recomendação excede o limite seguro de armazenamento.")
        item = PortfolioRecommendationRun(
            user_id=user_id,
            generated_at=result.generated_at,
            created_at=datetime.now(timezone.utc),
            engine_version=ENGINE_VERSION,
            policy_id=result.policy_id,
            status=result.status,
            selected_count=len(result.assets),
            considered_count=result.preflight.universe_considered,
            record_json=serialized,
            content_sha256=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )
        try:
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
        except Exception:
            self.db.rollback()
            raise
        return item

    def list_for_user(self, user_id: UUID, *, limit: int = 20, offset: int = 0) -> list[PortfolioRecommendationRun]:
        return (
            self.db.query(PortfolioRecommendationRun)
            .filter(PortfolioRecommendationRun.user_id == user_id)
            .order_by(PortfolioRecommendationRun.created_at.desc(), PortfolioRecommendationRun.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_for_user(self, user_id: UUID, run_id: UUID) -> PortfolioRecommendationRun | None:
        return (
            self.db.query(PortfolioRecommendationRun)
            .filter(
                PortfolioRecommendationRun.user_id == user_id,
                PortfolioRecommendationRun.id == run_id,
            )
            .first()
        )

    @staticmethod
    def verify(item: PortfolioRecommendationRun) -> dict:
        check = hashlib.sha256(item.record_json.encode("utf-8")).hexdigest()
        if check != item.content_sha256:
            raise ValueError("Registro histórico apresenta divergência de integridade.")
        return json.loads(item.record_json)
