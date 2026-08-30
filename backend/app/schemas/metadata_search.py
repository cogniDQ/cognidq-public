"""Pydantic schemas for Metadata Search Abstraction (F101)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# ── Enums ──────────────────────────────────────────────────────────────────


class AssetType:
    DATASET = "dataset"
    FIELD = "field"
    DATASOURCE = "datasource"

    ALL = ["dataset", "field", "datasource"]


class TrustLevel:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AUTHORITATIVE = "authoritative"

    ALL = ["low", "medium", "high", "authoritative"]


# ── Response objects ───────────────────────────────────────────────────────


class MetadataAsset(BaseModel):
    """Canonical metadata search result."""

    asset_id: UUID
    asset_type: str
    workspace_id: UUID
    name: str
    display_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    data_type: str | None = None
    parent_asset_id: UUID | None = None
    source_table: str
    source_id: UUID
    relevance_score: float = 0.0
    created_at: datetime | None = None


class MetadataTermResponse(BaseModel):
    """Glossary term response."""

    term_id: UUID
    workspace_id: UUID
    business_name: str
    technical_name: str | None = None
    definition: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    domain: str | None = None
    linked_asset_ids: list[str] = Field(default_factory=list)
    source: str = "manual"
    trust_level: str = "medium"
    relevance_score: float = 0.0
    created_at: datetime | None = None


# ── Request objects ────────────────────────────────────────────────────────


class MetadataTermCreate(BaseModel):
    """Create a glossary term."""

    business_name: str = Field(..., min_length=1, max_length=500)
    technical_name: str | None = Field(None, max_length=500)
    definition: str | None = Field(None, max_length=2000)
    synonyms: list[str] = Field(default_factory=list, max_length=50)
    domain: str | None = Field(None, max_length=100)
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
        if v not in TrustLevel.ALL:
            raise ValueError(f"trust_level must be one of {TrustLevel.ALL}")
        return v


# ── Aggregated responses ───────────────────────────────────────────────────


class MetadataSearchResponse(BaseModel):
    """Combined search results from asset and term indexes."""

    assets: list[MetadataAsset] = Field(default_factory=list)
    terms: list[MetadataTermResponse] = Field(default_factory=list)
    total: int = 0
    query: str = ""


class MetadataSyncResponse(BaseModel):
    """Stats from a metadata sync operation."""

    assets_created: int = 0
    assets_updated: int = 0
    total: int = 0
    workspace_id: UUID | None = None
