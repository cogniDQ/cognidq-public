"""
F036-P03  API Endpoints + Timeline Service
15 tests · POST comment endpoint, GET timeline endpoint, TimelineService
"""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.models.audit_log import AuditLog
from app.models.issue_comment import IssueComment
from app.services.issues.comment_models import (
    CommentResponse,
    TimelineEntry,
    TimelinePage,
)
from app.services.issues.comment_repository import IssueCommentRepository
from app.services.issues.timeline_service import TimelineService

ISSUES_EP = "app.api.v1.endpoints.issues"


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = uuid4()
    actor.actor_id = uuid4()
    actor.actor_role = "admin"
    return actor


def _mock_comment_response(**overrides):
    defaults = dict(
        id=uuid4(),
        issue_id=uuid4(),
        author_id=uuid4(),
        author_name="TestUser",
        body="Sample comment",
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return CommentResponse(**defaults)


# ---------------------------------------------------------------------------
# TestCommentEndpoint
# ---------------------------------------------------------------------------
class TestCommentEndpoint:
    @pytest.mark.asyncio
    async def test_post_comment_returns_201(self):
        from app.api.v1.endpoints.issues import add_comment

        resp = _mock_comment_response()
        with patch(f"{ISSUES_EP}._comment_svc") as mock_svc:
            mock_svc.add_comment.return_value = resp
            db = MagicMock()
            body = MagicMock()
            body.body = "Test comment"
            result = await add_comment(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                body=body,
                actor=_mock_actor(),
                db=db,
            )
        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_post_comment_empty_body_returns_422(self):
        from app.api.v1.endpoints.issues import add_comment
        from app.services.issues.comment_service import CommentBodyError
        from fastapi import HTTPException

        with patch(f"{ISSUES_EP}._comment_svc") as mock_svc:
            mock_svc.add_comment.side_effect = CommentBodyError("empty")
            body = MagicMock()
            body.body = ""
            with pytest.raises(HTTPException) as exc_info:
                await add_comment(
                    workspace_id=uuid4(),
                    issue_id=uuid4(),
                    body=body,
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_post_comment_nonexistent_issue_returns_404(self):
        from app.api.v1.endpoints.issues import add_comment
        from app.services.issues.comment_service import IssueNotFoundError
        from fastapi import HTTPException

        with patch(f"{ISSUES_EP}._comment_svc") as mock_svc:
            mock_svc.add_comment.side_effect = IssueNotFoundError("not found")
            body = MagicMock()
            body.body = "hello"
            with pytest.raises(HTTPException) as exc_info:
                await add_comment(
                    workspace_id=uuid4(),
                    issue_id=uuid4(),
                    body=body,
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_post_comment_response_has_author_name(self):
        import json

        from app.api.v1.endpoints.issues import add_comment

        resp = _mock_comment_response(author_name="Alice")
        with patch(f"{ISSUES_EP}._comment_svc") as mock_svc:
            mock_svc.add_comment.return_value = resp
            result = await add_comment(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                body=MagicMock(body="hi"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        content = json.loads(result.body)
        assert content["author_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_post_comment_calls_service(self):
        from app.api.v1.endpoints.issues import add_comment

        resp = _mock_comment_response()
        with patch(f"{ISSUES_EP}._comment_svc") as mock_svc:
            mock_svc.add_comment.return_value = resp
            await add_comment(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                body=MagicMock(body="call check"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        mock_svc.add_comment.assert_called_once()


# ---------------------------------------------------------------------------
# TestTimelineEndpoint
# ---------------------------------------------------------------------------
class TestTimelineEndpoint:
    @pytest.mark.asyncio
    async def test_timeline_returns_comments(self):
        import json

        from app.api.v1.endpoints.issues import get_timeline

        entries = [
            TimelineEntry(
                entry_type="comment",
                id=uuid4(),
                timestamp=datetime.now(UTC),
                actor_id=uuid4(),
                actor_name="Bob",
                content={"body": "hello"},
            ),
        ]
        page = TimelinePage(items=entries, total=1, page=1, page_size=50, has_next=False)
        with patch(f"{ISSUES_EP}._timeline_svc") as mock_svc:
            mock_svc.get_timeline.return_value = page
            result = await get_timeline(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                page=1,
                page_size=50,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        content = json.loads(result.body)
        assert len(content["items"]) == 1
        assert content["items"][0]["entry_type"] == "comment"

    @pytest.mark.asyncio
    async def test_timeline_returns_events(self):
        import json

        from app.api.v1.endpoints.issues import get_timeline

        entries = [
            TimelineEntry(
                entry_type="event",
                id=uuid4(),
                timestamp=datetime.now(UTC),
                actor_id=uuid4(),
                actor_name="System",
                content={"action": "issue_status_changed"},
            ),
        ]
        page = TimelinePage(items=entries, total=1, page=1, page_size=50, has_next=False)
        with patch(f"{ISSUES_EP}._timeline_svc") as mock_svc:
            mock_svc.get_timeline.return_value = page
            result = await get_timeline(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                page=1,
                page_size=50,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        content = json.loads(result.body)
        assert content["items"][0]["entry_type"] == "event"

    @pytest.mark.asyncio
    async def test_timeline_merged_sorted_by_time(self):
        import json

        from app.api.v1.endpoints.issues import get_timeline

        now = datetime.now(UTC)
        entries = [
            TimelineEntry(
                entry_type="comment", id=uuid4(), timestamp=now, content={"body": "newer"}
            ),
            TimelineEntry(
                entry_type="event",
                id=uuid4(),
                timestamp=now - timedelta(minutes=5),
                content={"action": "older"},
            ),
        ]
        page = TimelinePage(items=entries, total=2, page=1, page_size=50, has_next=False)
        with patch(f"{ISSUES_EP}._timeline_svc") as mock_svc:
            mock_svc.get_timeline.return_value = page
            result = await get_timeline(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                page=1,
                page_size=50,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        content = json.loads(result.body)
        assert content["items"][0]["timestamp"] > content["items"][1]["timestamp"]

    @pytest.mark.asyncio
    async def test_timeline_pagination(self):
        import json

        from app.api.v1.endpoints.issues import get_timeline

        page = TimelinePage(items=[], total=100, page=2, page_size=50, has_next=True)
        with patch(f"{ISSUES_EP}._timeline_svc") as mock_svc:
            mock_svc.get_timeline.return_value = page
            result = await get_timeline(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                page=2,
                page_size=50,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        content = json.loads(result.body)
        assert content["page"] == 2
        assert content["has_next"] is True

    @pytest.mark.asyncio
    async def test_timeline_empty_returns_empty_list(self):
        import json

        from app.api.v1.endpoints.issues import get_timeline

        page = TimelinePage(items=[], total=0, page=1, page_size=50, has_next=False)
        with patch(f"{ISSUES_EP}._timeline_svc") as mock_svc:
            mock_svc.get_timeline.return_value = page
            result = await get_timeline(
                workspace_id=uuid4(),
                issue_id=uuid4(),
                page=1,
                page_size=50,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        content = json.loads(result.body)
        assert content["items"] == []
        assert content["total"] == 0


# ---------------------------------------------------------------------------
# TestTimelineService
# ---------------------------------------------------------------------------
class TestTimelineService:
    def _make_comment(self, created_at=None, **kw):
        c = MagicMock(spec=IssueComment)
        c.id = kw.get("id", uuid4())
        c.author_id = kw.get("author_id", uuid4())
        c.body = kw.get("body", "test")
        c.created_at = created_at or datetime.now(UTC)
        return c

    def _make_audit(self, occurred_at=None, **kw):
        a = MagicMock(spec=AuditLog)
        a.log_id = kw.get("log_id", uuid4())
        a.actor_id = kw.get("actor_id", uuid4())
        a.action_type = kw.get("action_type", "issue_status_changed")
        a.previous_data = kw.get("previous_data", {"status": "open"})
        a.new_data = kw.get("new_data", {"status": "in_progress"})
        a.occurred_at = occurred_at or datetime.now(UTC)
        return a

    def _setup_db(self, comments, audit_rows, users=None):
        db = MagicMock()
        comment_repo = MagicMock()
        comment_repo.list_by_issue.return_value = (comments, len(comments))

        # Audit query chain
        MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            audit_rows
        )

        # User query chain (for actor names)
        if users is not None:
            user_query = MagicMock()
            user_query.filter.return_value.all.return_value = users

            # Override the second query call
            def _query_side_effect(model, *extra):
                if (
                    hasattr(model, "__tablename__")
                    and model.__tablename__ == "workspace_audit_logs"
                ):
                    return db.query.return_value
                # User query
                result = MagicMock()
                result.filter.return_value.all.return_value = users
                return result

            # Simpler: just configure the filter chain for User queries
            pass

        return db, comment_repo

    def test_timeline_service_merges_sources(self):
        now = datetime.now(UTC)
        comments = [self._make_comment(created_at=now)]
        audits = [self._make_audit(occurred_at=now - timedelta(seconds=30))]
        db, repo = self._setup_db(comments, audits)

        svc = TimelineService(comment_repo=repo)
        result = svc.get_timeline(db, uuid4(), uuid4())
        assert result.total == 2
        assert result.items[0].entry_type == "comment"
        assert result.items[1].entry_type == "event"

    def test_timeline_service_sorts_descending(self):
        now = datetime.now(UTC)
        old = now - timedelta(hours=1)
        comments = [self._make_comment(created_at=old)]
        audits = [self._make_audit(occurred_at=now)]
        db, repo = self._setup_db(comments, audits)

        svc = TimelineService(comment_repo=repo)
        result = svc.get_timeline(db, uuid4(), uuid4())
        assert result.items[0].timestamp > result.items[1].timestamp

    def test_timeline_service_paginates_correctly(self):
        now = datetime.now(UTC)
        comments = [self._make_comment(created_at=now - timedelta(seconds=i)) for i in range(5)]
        db, repo = self._setup_db(comments, [])

        svc = TimelineService(comment_repo=repo)
        result = svc.get_timeline(db, uuid4(), uuid4(), page=1, page_size=3)
        assert len(result.items) == 3
        assert result.total == 5
        assert result.has_next is True

        result2 = svc.get_timeline(db, uuid4(), uuid4(), page=2, page_size=3)
        assert len(result2.items) == 2
        assert result2.has_next is False

    def test_timeline_service_resolves_actor_names(self):
        now = datetime.now(UTC)
        author_id = uuid4()
        comments = [self._make_comment(created_at=now, author_id=author_id)]
        db, repo = self._setup_db(comments, [])

        # Mock User query for name resolution
        user_mock = MagicMock()
        user_mock.id = author_id
        user_mock.full_name = "Alice Wonder"
        user_mock.email = "alice@test.com"

        # Configure user query chain
        user_query_chain = MagicMock()
        user_query_chain.filter.return_value.all.return_value = [user_mock]

        call_count = [0]
        original_query = db.query.return_value

        def _query_dispatch(*args):
            call_count[0] += 1
            if call_count[0] <= 1:
                # First db.query call is from audit (AuditLog)
                return original_query
            # Second is User query
            return user_query_chain

        db.query.side_effect = _query_dispatch

        svc = TimelineService(comment_repo=repo)
        result = svc.get_timeline(db, uuid4(), uuid4())
        assert result.items[0].actor_name == "Alice Wonder"

    def test_timeline_service_handles_no_audit_events(self):
        now = datetime.now(UTC)
        comments = [self._make_comment(created_at=now)]
        db, repo = self._setup_db(comments, [])

        svc = TimelineService(comment_repo=repo)
        result = svc.get_timeline(db, uuid4(), uuid4())
        assert result.total == 1
        assert result.items[0].entry_type == "comment"
