"""
F036-P02  Comment Service + Audit Integration
15 tests · IssueCommentService, audit hooks, audit constants
"""

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.models.issue_comment import IssueComment
from app.services.audit.constants import VALID_ACTION_TYPES, VALID_ENTITY_TYPES
from app.services.audit.hooks import build_comment_audit_entry
from app.services.audit.models import AuditContext
from app.services.issues.comment_models import CommentResponse
from app.services.issues.comment_service import (
    CommentBodyError,
    IssueCommentService,
    IssueNotFoundError,
)

SVC_MOD = "app.services.issues.comment_service"


def _make_service(issue_exists=True):
    """Build IssueCommentService with mocked dependencies."""
    comment_repo = MagicMock()
    issue_repo = MagicMock()
    audit_svc = MagicMock()

    if issue_exists:
        issue_repo.get_by_id_and_workspace.return_value = MagicMock(
            id=uuid4(),
            tenant_id=uuid4(),
        )
    else:
        issue_repo.get_by_id_and_workspace.return_value = None

    # Make insert return the comment with populated fields
    def _insert_side_effect(db, comment):
        comment.id = uuid4()
        comment.created_at = datetime.now(UTC)
        comment.author = None
        return comment

    comment_repo.insert.side_effect = _insert_side_effect

    svc = IssueCommentService(
        comment_repo=comment_repo,
        issue_repo=issue_repo,
        audit_service=audit_svc,
    )
    return svc, comment_repo, issue_repo, audit_svc


def _audit_ctx():
    return AuditContext(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_type="user",
        actor_role="admin",
        request_id=uuid4(),
        source_ip="127.0.0.1",
    )


# ---------------------------------------------------------------------------
# TestCommentService
# ---------------------------------------------------------------------------
class TestCommentService:
    def test_add_comment_happy_path(self):
        svc, repo, _, _ = _make_service()
        result = svc.add_comment(
            MagicMock(),
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=uuid4(),
            body="Hello world",
        )
        assert isinstance(result, CommentResponse)

    def test_add_comment_returns_response(self):
        svc, *_ = _make_service()
        result = svc.add_comment(
            MagicMock(),
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=uuid4(),
            body="Test body",
        )
        assert result.body == "Test body"

    def test_add_comment_issue_not_found_raises(self):
        svc, *_ = _make_service(issue_exists=False)
        with pytest.raises(IssueNotFoundError):
            svc.add_comment(
                MagicMock(),
                issue_id=uuid4(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                author_id=uuid4(),
                body="hello",
            )

    def test_add_comment_body_too_short_raises(self):
        svc, *_ = _make_service()
        with pytest.raises(CommentBodyError):
            svc.add_comment(
                MagicMock(),
                issue_id=uuid4(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                author_id=uuid4(),
                body="   ",
            )

    def test_add_comment_body_too_long_raises(self):
        svc, *_ = _make_service()
        with pytest.raises(CommentBodyError):
            svc.add_comment(
                MagicMock(),
                issue_id=uuid4(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                author_id=uuid4(),
                body="x" * 10_001,
            )

    def test_add_comment_calls_repo_insert(self):
        svc, comment_repo, _, _ = _make_service()
        db = MagicMock()
        svc.add_comment(
            db,
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=uuid4(),
            body="note",
        )
        comment_repo.insert.assert_called_once()
        args = comment_repo.insert.call_args[0]
        assert args[0] is db
        assert isinstance(args[1], IssueComment)

    def test_add_comment_writes_audit_entry(self):
        svc, _, _, audit_svc = _make_service()
        db = MagicMock()
        ctx = _audit_ctx()
        svc.add_comment(
            db,
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=uuid4(),
            body="audited",
            audit_ctx=ctx,
        )
        audit_svc.write.assert_called_once()

    def test_add_comment_audit_action_type(self):
        svc, _, _, audit_svc = _make_service()
        ctx = _audit_ctx()
        svc.add_comment(
            MagicMock(),
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=uuid4(),
            body="test",
            audit_ctx=ctx,
        )
        entry = audit_svc.write.call_args[0][1]
        assert entry.action_type == "issue_comment_added"

    def test_add_comment_populates_author_id(self):
        svc, *_ = _make_service()
        aid = uuid4()
        result = svc.add_comment(
            MagicMock(),
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=aid,
            body="mine",
        )
        assert result.author_id == aid

    def test_add_comment_populates_tenant_workspace(self):
        svc, comment_repo, _, _ = _make_service()
        ws = uuid4()
        tid = uuid4()
        svc.add_comment(
            MagicMock(),
            issue_id=uuid4(),
            workspace_id=ws,
            tenant_id=tid,
            author_id=uuid4(),
            body="check",
        )
        inserted = comment_repo.insert.call_args[0][1]
        assert inserted.workspace_id == ws
        assert inserted.tenant_id == tid


# ---------------------------------------------------------------------------
# TestCommentAudit
# ---------------------------------------------------------------------------
class TestCommentAudit:
    def test_build_comment_audit_entry_structure(self):
        ctx = _audit_ctx()
        entry = build_comment_audit_entry(
            ctx=ctx,
            action="issue_comment_added",
            workspace_id=uuid4(),
            comment_id=uuid4(),
            after_state={"body": "test"},
        )
        assert entry.action_type == "issue_comment_added"
        assert entry.target_entity_type == "issue_comment"

    def test_build_comment_audit_entry_entity_type(self):
        ctx = _audit_ctx()
        entry = build_comment_audit_entry(
            ctx=ctx,
            action="issue_comment_added",
            workspace_id=uuid4(),
            comment_id=uuid4(),
            after_state={"body": "x"},
        )
        assert entry.target_entity_type == "issue_comment"

    def test_build_comment_audit_entry_action(self):
        ctx = _audit_ctx()
        entry = build_comment_audit_entry(
            ctx=ctx,
            action="issue_comment_added",
            workspace_id=uuid4(),
            comment_id=uuid4(),
            after_state={},
        )
        assert entry.action_type == "issue_comment_added"

    def test_audit_constants_include_comment_added(self):
        assert "issue_comment_added" in VALID_ACTION_TYPES

    def test_audit_constants_include_comment_entity(self):
        assert "issue_comment" in VALID_ENTITY_TYPES
