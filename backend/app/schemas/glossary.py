"""Pydantic schemas for Business Glossary Management (F109)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.metadata_search import MetadataTermResponse


class GlossaryTermCreate(BaseModel):
    """Create a glossary term (F109)."""

    business_name: str = Field(..., min_length=1, max_length=500)
    technical_name: str | None = Field(None, max_length=500)
    definition: str | None = Field(None, max_length=2000)
    domain: str | None = Field(None, max_length=100)
    synonyms: list[str] = Field(default_factory=list)
    data_type: str | None = Field(None, max_length=50)
    owner: str | None = Field(None, max_length=255)
    is_mandatory: bool = Field(False)
    allowed_values: list[str] | None = Field(None)
    linked_asset_ids: list[str] = Field(default_factory=list)
    trust_level: str = Field("medium")

    @field_validator("business_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("business_name must not be blank")
        return v

    @field_validator("trust_level")
    @classmethod
    def validate_trust(cls, v: str) -> str:
        allowed = ["low", "medium", "high", "authoritative"]
        if v not in allowed:
            raise ValueError(f"trust_level must be one of {allowed}")
        return v


class GlossaryTermUpdate(BaseModel):
    """Update a glossary term (F109)."""

    business_name: str | None = Field(None, min_length=1, max_length=500)
    technical_name: str | None = Field(None, max_length=500)
    definition: str | None = Field(None, max_length=2000)
    domain: str | None = Field(None, max_length=100)
    synonyms: list[str] | None = None
    data_type: str | None = Field(None, max_length=50)
    owner: str | None = Field(None, max_length=255)
    is_mandatory: bool | None = None
    allowed_values: list[str] | None = None
    linked_asset_ids: list[str] | None = None
    trust_level: str | None = None

    @field_validator("trust_level")
    @classmethod
    def validate_trust(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = ["low", "medium", "high", "authoritative"]
        if v not in allowed:
            raise ValueError(f"trust_level must be one of {allowed}")
        return v


class GlossaryTermResponse(MetadataTermResponse):
    """Extended glossary term response with F109 fields."""

    data_type: str | None = None
    owner: str | None = None
    is_mandatory: bool = False
    allowed_values: list[str] | None = None
    tenant_id: UUID | None = None


class GlossaryListResponse(BaseModel):
    """Paginated glossary list response."""

    items: list[GlossaryTermResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class GlossaryImportResult(BaseModel):
    """Result of a CSV import operation."""

    imported: int = 0
    skipped: int = 0
    errors: list[dict] = Field(default_factory=list)


class GlossarySearchRequest(BaseModel):
    """Search request for glossary terms."""

    query: str = Field(..., min_length=1, max_length=500)
    domain: str | None = None
    limit: int = Field(20, ge=1, le=200)
