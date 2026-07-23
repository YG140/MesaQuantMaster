from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CvmSyncRequest(BaseModel):
    document_type: str = Field(pattern="^(DFP|ITR)$")
    year: int = Field(ge=2010, le=2100)


class CvmSyncAccepted(BaseModel):
    status: str
    message: str
    document_type: str
    year: int


class CvmSyncStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_type: str
    year: int
    status: str
    documents_imported: int
    accounts_imported: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class CvmIssuerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cnpj: str
    cvm_code: str
    official_name: str


class AssetCvmLinkUpdate(BaseModel):
    issuer_id: UUID


class AssetCvmLinkResponse(BaseModel):
    asset_id: UUID
    status: str
    reason: str | None
    issuer: CvmIssuerResponse | None


class CvmAvailableDocument(BaseModel):
    document_type: str
    year: int
