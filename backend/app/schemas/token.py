"""
Personal Access Token schemas
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateTokenRequest(BaseModel):
    """Request to create a new access token"""

    name: str = Field(..., min_length=1, max_length=255, description="Token name/description")
    expires_in_days: int | None = Field(
        None, ge=1, le=365, description="Token expiration in days (1-365)"
    )
    scopes: list[str] | None = Field(default=[], description="Token scopes/permissions")


class TokenResponse(BaseModel):
    """Access token response"""

    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None
    is_valid: bool

    class Config:
        from_attributes = True


class CreateTokenResponse(TokenResponse):
    """Response when creating a new token (includes the plain token)"""

    token: str

    class Config:
        from_attributes = True


class TokenListResponse(BaseModel):
    """List of access tokens"""

    tokens: list[TokenResponse]
    total: int
