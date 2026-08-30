"""
F036-P01  Migration + Model + Repository + Schemas
15 tests · IssueComment ORM, Pydantic schemas, IssueCommentRepository
"""

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest
from app.models.issue_comment import IssueComment
from app.services.issues.comment_models import (
    CommentResponse,
    CreateCommentRequest,
    TimelineEntry,
    TimelinePage,
)
from app.services.issues.comment_repository import IssueCommentRepository


# ---------------------------------------------------------------------------
# TestIssueCommentModel
# ---------------------------------------------------------------------------
class TestIssueCommentModel:
    def test_orm_model_has_expected_columns(self):
        cols = {c.name for c in IssueComment.__table__.columns}
        expected = {
            "id",
            "issue_id",
            "workspace_id",
            "tenant_id",
            "author_id",
            "body",
            "created_at",
        }
        assert expected == cols

    def test_orm_model_tablename(self):
        assert IssueComment.__tablename__ == "issue_comments"

    def test_orm_model_default_id(self):
        col = IssueComment.__table__.c.id
        assert col.default is not None
        assert callable(col.default.arg)

    def test_orm_model_author_relationship(self):
        rels = {r.key for r in IssueComment.__mapper__.relationships}
        assert "author" in rels


# ---------------------------------------------------------------------------
# TestCommentSchemas
# ---------------------------------------------------------------------------
class TestCommentSchemas:
    def test_create_request_valid(self):
        req = CreateCommentRequest(body="This is a valid comment.")
        assert req.body == "This is a valid comment."

    def test_create_request_empty_body_rejected(self):
        with pytest.raises(Exception):
            CreateCommentRequest(body="")

    def test_create_request_too_long_body_rejected(self):
        with pytest.raises(Exception):
            CreateCommentRequest(body="x" * 10_001)

    def test_comment_response_from_attributes(self):
        now = datetime.now(UTC)
        resp = CommentResponse(
            id=uuid4(),
            issue_id=uuid4(),
            author_id=uuid4(),
            author_name="Alice",
            body="hello",
            created_at=now,
        )
        assert resp.body == "hello"
        assert resp.author_name == "Alice"

    def test_timeline_entry_comment_type(self):
        entry = TimelineEntry(
            entry_type="comment",
            id=uuid4(),
            timestamp=datetime.now(UTC),
            actor_id=uuid4(),
            actor_name="Bob",
            content={"body": "test"},
        )
        assert entry.entry_type == "comment"

    def test_timeline_entry_event_type(self):
        entry = TimelineEntry(
            entry_type="event",
            id=uuid4(),
            timestamp=datetime.now(UTC),
            actor_id=uuid4(),
            actor_name="System",
            content={"action": "issue_status_changed", "before": {}, "after": {}},
        )
        assert entry.entry_type == "event"

    def test_timeline_page_has_next(self):
        page = TimelinePage(
            items=[],
            total=100,
            page=1,
            page_size=50,
            has_next=True,
        )
        assert page.has_next is True
        page2 = TimelinePage(
            items=[],
            total=10,
            page=1,
            page_size=50,
            has_next=False,
        )
        assert page2.has_next is False


# ---------------------------------------------------------------------------
# TestCommentRepository
# ---------------------------------------------------------------------------
class TestCommentRepository:
    def _make_comment(self, **overrides):
        defaults = dict(
            issue_id=uuid4(),
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            author_id=uuid4(),
            body="test comment",
        )
        defaults.update(overrides)
        return IssueComment(**defaults)

    def test_repo_insert_calls_flush(self):
        db = MagicMock()
        repo = IssueCommentRepository()
        comment = self._make_comment()
        repo.insert(db, comment)
        db.add.assert_called_once_with(comment)
        db.flush.assert_called_once()

    def test_repo_insert_returns_orm(self):
        db = MagicMock()
        repo = IssueCommentRepository()
        comment = self._make_comment()
        result = repo.insert(db, comment)
        assert result is comment

    def test_repo_list_by_issue_returns_tuple(self):
        db = MagicMock()
        issue_id = uuid4()
        # Build mock query chain
        mock_query = MagicMock()
        db.query.return_value.filter.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            self._make_comment(),
            self._make_comment(),
        ]
        repo = IssueCommentRepository()
        items, total = repo.list_by_issue(db, issue_id)
        assert total == 2
        assert len(items) == 2

    def test_repo_list_by_issue_applies_offset_limit(self):
        db = MagicMock()
        issue_id = uuid4()
        mock_query = MagicMock()
        db.query.return_value.filter.return_value = mock_query
        mock_query.count.return_value = 0
        ordered = MagicMock()
        mock_query.order_by.return_value = ordered
        ordered.offset.return_value.limit.return_value.all.return_value = []

        repo = IssueCommentRepository()
        repo.list_by_issue(db, issue_id, offset=10, limit=25)
        ordered.offset.assert_called_once_with(10)
        ordered.offset.return_value.limit.assert_called_once_with(25)
