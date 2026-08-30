"""Pydantic schemas for domains."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


def slugify(name: str) -> str:
    """Convert name to URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug


class DomainBase(BaseModel):
    """Base domain schema."""

    name: str = Field(..., min_length=1, max_length=255, description="Domain name")
    description: str | None = Field(None, description="Domain description")
    slug: str | None = Field(None, min_length=1, max_length=100, description="URL-safe slug")
    metadata: dict[str, Any] | None = Field(default_factory=dict)

    @validator("slug", pre=True, always=True)
    def generate_slug(cls, v, values):
        """Auto-generate slug from name if not provided."""
        if v:
            return v
        if "name" in values:
            return slugify(values["name"])
        return None


class CreateDomainRequest(DomainBase):
    """Request schema for creating a domain."""

    pass


class UpdateDomainRequest(BaseModel):
    """Request schema for updating a domain."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    slug: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class DomainResponse(DomainBase):
    """Response schema for domain."""

    id: UUID
    workspace_id: UUID
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    teams_count: int | None = Field(None, description="Number of teams in domain")

    class Config:
        from_attributes = True


class DomainWithTeams(DomainResponse):
    """Domain response with teams included."""

    teams: list = Field(default_factory=list, description="Teams in this domain")

    class Config:
        from_attributes = True
