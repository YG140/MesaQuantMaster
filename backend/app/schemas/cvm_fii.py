from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CvmFiiSyncRequest(BaseModel):
    year: int = Field(ge=2021, le=2100)


class CvmFiiSyncAccepted(BaseModel):
    status: str
    message: str
    year: int


class CvmFiiSyncStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_type: str
    year: int
    status: str
    documents_imported: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
