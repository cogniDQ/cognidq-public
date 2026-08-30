"""
Personal Access Token service
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.access_token import AccessToken


class AccessTokenService:
    """Service for managing Personal Access Tokens"""

    TOKEN_PREFIX_LENGTH = 8
    TOKEN_LENGTH = 40

    @staticmethod
    def generate_token() -> tuple[str, str, str]:
        """
        Generate a new token
        Returns: (full_token, token_hash, prefix)
        """
        # Generate random token
        raw_token = secrets.token_urlsafe(AccessTokenService.TOKEN_LENGTH)

        # Create prefix for easy identification (first 8 chars)
        prefix = raw_token[: AccessTokenService.TOKEN_PREFIX_LENGTH]

        # Hash the token for storage
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        return f"dqai_{raw_token}", token_hash, f"dqai_{prefix}"

    @staticmethod
    def create_token(
        db: Session,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_in_days: int | None = None,
    ) -> tuple[AccessToken, str]:
        """
        Create a new personal access token
        Returns: (AccessToken model, plain_token)
        """
        # Generate token
        plain_token, token_hash, prefix = AccessTokenService.generate_token()

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        # Create token record
        token = AccessToken(
            user_id=user_id,
            name=name,
            token_hash=token_hash,
            prefix=prefix,
            scopes=scopes or [],
            expires_at=expires_at,
        )

        db.add(token)
        db.commit()
        db.refresh(token)

        return token, plain_token

    @staticmethod
    def list_tokens(db: Session, user_id: str) -> list[AccessToken]:
        """List all tokens for a user (excluding revoked)"""
        return (
            db.query(AccessToken)
            .filter(AccessToken.user_id == user_id, AccessToken.revoked_at.is_(None))
            .order_by(AccessToken.created_at.desc())
            .all()
        )

    @staticmethod
    def list_all_tokens(db: Session, user_id: str) -> list[AccessToken]:
        """List all tokens for a user (including revoked)"""
        return (
            db.query(AccessToken)
            .filter(AccessToken.user_id == user_id)
            .order_by(AccessToken.created_at.desc())
            .all()
        )

    @staticmethod
    def get_token_by_hash(db: Session, token_hash: str) -> AccessToken | None:
        """Get token by hash"""
        return db.query(AccessToken).filter(AccessToken.token_hash == token_hash).first()

    @staticmethod
    def verify_token(db: Session, plain_token: str) -> AccessToken | None:
        """
        Verify a token and return the token object if valid
        """
        # Hash the provided token
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()

        # Find token
        token = AccessTokenService.get_token_by_hash(db, token_hash)

        if not token or not token.is_valid():
            return None

        # Update last used timestamp
        token.last_used_at = datetime.utcnow()
        db.commit()

        return token

    @staticmethod
    def revoke_token(db: Session, token_id: str, user_id: str) -> bool:
        """Revoke a token"""
        token = (
            db.query(AccessToken)
            .filter(AccessToken.id == token_id, AccessToken.user_id == user_id)
            .first()
        )

        if not token:
            return False

        token.revoked_at = datetime.utcnow()
        db.commit()
        return True

    @staticmethod
    def delete_token(db: Session, token_id: str, user_id: str) -> bool:
        """Permanently delete a token"""
        token = (
            db.query(AccessToken)
            .filter(AccessToken.id == token_id, AccessToken.user_id == user_id)
            .first()
        )

        if not token:
            return False

        db.delete(token)
        db.commit()
        return True
