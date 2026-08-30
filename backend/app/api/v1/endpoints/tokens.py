"""
Personal Access Token API endpoints
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.token import (
    CreateTokenRequest,
    CreateTokenResponse,
    TokenListResponse,
    TokenResponse,
)
from app.services.auth.jwt import get_current_user
from app.services.auth.token_service import AccessTokenService

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.post("", response_model=CreateTokenResponse, status_code=status.HTTP_201_CREATED)
def create_token(
    request: CreateTokenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new personal access token"""
    token_model, plain_token = AccessTokenService.create_token(
        db=db,
        user_id=str(current_user.id),
        name=request.name,
        scopes=request.scopes,
        expires_in_days=request.expires_in_days,
    )

    # Build response with plain token
    return CreateTokenResponse(
        id=token_model.id,
        name=token_model.name,
        prefix=token_model.prefix,
        scopes=token_model.scopes or [],
        expires_at=token_model.expires_at,
        last_used_at=token_model.last_used_at,
        created_at=token_model.created_at,
        revoked_at=token_model.revoked_at,
        is_valid=token_model.is_valid(),
        token=plain_token,
    )


@router.get("", response_model=TokenListResponse)
def list_tokens(
    include_revoked: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all personal access tokens for the current user"""
    if include_revoked:
        tokens = AccessTokenService.list_all_tokens(db, str(current_user.id))
    else:
        tokens = AccessTokenService.list_tokens(db, str(current_user.id))

    return TokenListResponse(
        tokens=[
            TokenResponse(
                id=t.id,
                name=t.name,
                prefix=t.prefix,
                scopes=t.scopes or [],
                expires_at=t.expires_at,
                last_used_at=t.last_used_at,
                created_at=t.created_at,
                revoked_at=t.revoked_at,
                is_valid=t.is_valid(),
            )
            for t in tokens
        ],
        total=len(tokens),
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Revoke a personal access token"""
    success = AccessTokenService.revoke_token(db, str(token_id), str(current_user.id))

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    return None


@router.get("/{token_id}", response_model=TokenResponse)
def get_token(
    token_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get details of a specific token"""
    from app.models.access_token import AccessToken

    token = (
        db.query(AccessToken)
        .filter(AccessToken.id == token_id, AccessToken.user_id == current_user.id)
        .first()
    )

    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    return TokenResponse(
        id=token.id,
        name=token.name,
        prefix=token.prefix,
        scopes=token.scopes or [],
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
        created_at=token.created_at,
        revoked_at=token.revoked_at,
        is_valid=token.is_valid(),
    )
