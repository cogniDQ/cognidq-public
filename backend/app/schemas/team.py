"""Pydantic schemas for teams."""

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


class TeamBase(BaseModel):
    """Base team schema."""

    name: str = Field(..., min_length=1, max_length=255, description="Team name")
    description: str | None = Field(None, description="Team description")
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


class CreateTeamRequest(TeamBase):
    """Request schema for creating a team."""

    domain_id: UUID = Field(..., description="Domain ID this team belongs to")


class UpdateTeamRequest(BaseModel):
    """Request schema for updating a team."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    slug: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class TeamMemberBase(BaseModel):
    """Base team member schema."""

    user_id: UUID
    role: str = Field(default="member", description="Role in team: team-lead or member")


class AddTeamMemberRequest(TeamMemberBase):
    """Request schema for adding a member to team."""

    pass


class UpdateTeamMemberRequest(BaseModel):
    """Request schema for updating team member role."""

    role: str = Field(..., description="Role in team: team-lead or member")


class TeamMemberResponse(TeamMemberBase):
    """Response schema for team member."""

    email: str | None = None
    full_name: str | None = None
    joined_at: datetime

    class Config:
        from_attributes = True


class TeamResponse(TeamBase):
    """Response schema for team."""

    id: UUID
    domain_id: UUID
    workspace_id: UUID
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    members_count: int | None = Field(None, description="Number of members in team")

    class Config:
        from_attributes = True


class TeamWithMembers(TeamResponse):
    """Team response with members included."""

    members: list[TeamMemberResponse] = Field(default_factory=list, description="Team members")

    class Config:
        from_attributes = True


class TeamHierarchyResponse(BaseModel):
    """Hierarchical team structure response."""

    workspace_id: UUID
    organization_name: str
    domains: list[dict[str, Any]] = Field(default_factory=list)

    class Config:
        from_attributes = True
