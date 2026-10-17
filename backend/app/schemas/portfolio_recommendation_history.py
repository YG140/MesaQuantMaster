"""User-scoped, read-only views of saved portfolio recommendation decisions."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class RecommendationHistorySummary(BaseModel):
    id: UUID
    generated_at: datetime
    created_at: datetime
    engine_version: str
    status: str
    selected_count: int
    considered_count: int
    content_sha256: str


class RecommendationHistoryDetail(RecommendationHistorySummary):
    record: dict[str, Any]
    integrity_verified: bool = True
