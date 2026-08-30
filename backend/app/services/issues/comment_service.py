"""
F036 Issue Comment Service
===========================

Business logic for adding immutable comments to issues.  Validates issue
existence, persists the comment, and writes an audit entry — all within
the caller's transaction.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.issue_comment import IssueComment
from app.services.audit.hooks import build_comment_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.issues.comment_models import CommentResponse
from app.services.issues.comment_repository import IssueCommentRepository
from app.services.issues.issue_repository import IssueRepository

logger = logging.getLogger(__name__)


class IssueNotFoundError(Exception):
    """Raised when the target issue does not exist in the workspace."""


class CommentBodyError(Exception):
    """Raised when comment body is empty or exceeds the limit."""


class IssueCommentService:
    """Add immutable comments to data-quality issues."""

    _MAX_BODY_LENGTH = 10_000

    def __init__(
        self,
        *,
        comment_repo: IssueCommentRepository | None = None,
        issue_repo: IssueRepository | None = None,
        audit_service: AuditService | None = None,
    ):
        self._comment_repo = comment_repo or IssueCommentRepository()
        self._issue_repo = issue_repo or IssueRepository()
        self._audit_svc = audit_service or AuditService()

    def add_comment(
        self,
        db: Session,
        *,
        issue_id: UUID,
        workspace_id: UUID,
        tenant_id: UUID,
        author_id: UUID,
        body: str,
        audit_ctx: AuditContext | None = None,
    ) -> CommentResponse:
        """
        Add a comment to an issue.

        1. Validate body length
        2. Verify issue exists in workspace
        3. Persist IssueComment
        4. Write audit entry
        5. Return CommentResponse
        """
        # --- Validate body ---
        stripped = body.strip() if body else ""
        if len(stripped) < 1:
            raise CommentBodyError("Comment body must not be empty.")
        if len(stripped) > self._MAX_BODY_LENGTH:
            raise CommentBodyError(
                f"Comment body must not exceed {self._MAX_BODY_LENGTH} characters."
            )

        # --- Verify issue exists ---
        issue = self._issue_repo.get_by_id_and_workspace(db, issue_id, workspace_id)
        if issue is None:
            raise IssueNotFoundError(f"Issue {issue_id} not found in workspace {workspace_id}.")

        # --- Persist comment ---
        comment = IssueComment(
            issue_id=issue_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            author_id=author_id,
            body=stripped,
        )
        comment = self._comment_repo.insert(db, comment)

        # --- Audit ---
        if audit_ctx is not None:
            entry = build_comment_audit_entry(
                ctx=audit_ctx,
                action="issue_comment_added",
                workspace_id=workspace_id,
                comment_id=comment.id,
                after_state={
                    "issue_id": str(issue_id),
                    "body": stripped[:200],  # truncate for audit
                },
            )
            self._audit_svc.write(db, entry)

        # --- Build response ---
        author_name: str | None = None
        if comment.author is not None:
            author_name = getattr(comment.author, "full_name", None) or getattr(
                comment.author, "email", None
            )

        return CommentResponse(
            id=comment.id,
            issue_id=comment.issue_id,
            author_id=comment.author_id,
            author_name=author_name,
            body=comment.body,
            created_at=comment.created_at,
        )
