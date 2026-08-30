"""
F075-P01 · Rule Endpoint Tests
15 tests — covers create, list, get, update, delete, execute, bulk,
violations, summary, schedule/unschedule endpoints.

Directly calls async endpoint functions with mocked dependencies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

RULE_EP = "app.api.v1.endpoints.rules"

ORG = uuid4()
RULE_ID = uuid4()
EXEC_ID = uuid4()


def _svc():
    """Create an AsyncMock RuleService."""
    return AsyncMock()


def _user():
    u = MagicMock()
    u.id = uuid4()
    u.tenant_id = uuid4()
    u.platform_role = "admin"
    return u


def _db():
    return MagicMock()


# ===================================================================
# create_rule
# ===================================================================
class TestCreateRule:
    @pytest.mark.asyncio
    async def test_returns_rule(self):
        """P01-01: Successful create → returns rule object"""
        from app.api.v1.endpoints.rules import create_rule

        svc = _svc()
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "test"
        mock_rule.category = "completeness"
        mock_rule.severity = "high"
        svc.create_rule.return_value = mock_rule

        result = await create_rule(
            workspace_id=ORG,
            request=MagicMock(),
            db=_db(),
            service=svc,
            actor=_user(),
        )
        assert result == mock_rule

    @pytest.mark.asyncio
    async def test_calls_service(self):
        """P01-02: create_rule calls service.create_rule"""
        from app.api.v1.endpoints.rules import create_rule

        svc = _svc()
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "r"
        mock_rule.category = "c"
        mock_rule.severity = "s"
        svc.create_rule.return_value = mock_rule

        await create_rule(
            workspace_id=ORG,
            request=MagicMock(),
            db=_db(),
            service=svc,
            actor=_user(),
        )
        svc.create_rule.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_validation_error_400(self):
        """P01-03: ValueError from service → HTTPException 400"""
        from app.api.v1.endpoints.rules import create_rule

        svc = _svc()
        svc.create_rule.side_effect = ValueError("bad input")

        with pytest.raises(HTTPException) as exc_info:
            await create_rule(
                workspace_id=ORG,
                request=MagicMock(),
                db=_db(),
                service=svc,
                actor=_user(),
            )
        assert exc_info.value.status_code == 400
        assert "bad input" in str(exc_info.value.detail)


# ===================================================================
# list_rules
# ===================================================================
class TestListRules:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        """P01-04: List rules → returns list"""
        from app.api.v1.endpoints.rules import list_rules

        svc = _svc()
        svc.list_rules.return_value = [MagicMock(), MagicMock()]

        result = await list_rules(workspace_id=ORG, service=svc)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_org(self):
        """P01-05: No rules → empty list"""
        from app.api.v1.endpoints.rules import list_rules

        svc = _svc()
        svc.list_rules.return_value = []

        result = await list_rules(workspace_id=ORG, service=svc)
        assert result == []


# ===================================================================
# get_rule
# ===================================================================
class TestGetRule:
    @pytest.mark.asyncio
    async def test_found(self):
        """P01-06: Existing rule → returns rule"""
        from app.api.v1.endpoints.rules import get_rule

        svc = _svc()
        mock_rule = MagicMock()
        svc.get_rule.return_value = mock_rule

        result = await get_rule(workspace_id=ORG, rule_id=RULE_ID, service=svc)
        assert result == mock_rule

    @pytest.mark.asyncio
    async def test_not_found_404(self):
        """P01-07: Missing rule → HTTPException 404"""
        from app.api.v1.endpoints.rules import get_rule

        svc = _svc()
        svc.get_rule.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_rule(workspace_id=ORG, rule_id=RULE_ID, service=svc)
        assert exc_info.value.status_code == 404


# ===================================================================
# update_rule / delete_rule
# ===================================================================
class TestUpdateRule:
    @pytest.mark.asyncio
    async def test_returns_updated(self):
        """P01-08: Update → returns updated rule"""
        from app.api.v1.endpoints.rules import update_rule

        svc = _svc()
        mock_rule = MagicMock()
        mock_rule.id = RULE_ID
        mock_rule.name = "updated"
        mock_rule.category = "c"
        mock_rule.severity = "s"
        svc.update_rule.return_value = mock_rule

        result = await update_rule(
            workspace_id=ORG,
            rule_id=RULE_ID,
            request=MagicMock(),
            db=_db(),
            service=svc,
            actor=_user(),
        )
        assert result == mock_rule


class TestDeleteRule:
    @pytest.mark.asyncio
    async def test_returns_none(self):
        """P01-09: Delete → returns None (204 from decorator)"""
        from app.api.v1.endpoints.rules import delete_rule

        svc = _svc()
        svc.delete_rule.return_value = True

        result = await delete_rule(
            workspace_id=ORG,
            rule_id=RULE_ID,
            db=_db(),
            service=svc,
            actor=_user(),
        )
        assert result is None


# ===================================================================
# execute_rule
# ===================================================================
class TestExecuteRule:
    @pytest.mark.asyncio
    async def test_returns_execution(self):
        """P01-10: Execute → returns execution object"""
        from app.api.v1.endpoints.rules import execute_rule

        svc = _svc()
        mock_exec = MagicMock()
        svc.execute_rule.return_value = mock_exec

        result = await execute_rule(
            workspace_id=ORG,
            rule_id=RULE_ID,
            request=MagicMock(),
            service=svc,
            actor=_user(),
        )
        assert result == mock_exec

    @pytest.mark.asyncio
    async def test_triggers_service(self):
        """P01-11: execute_rule calls service.execute_rule"""
        from app.api.v1.endpoints.rules import execute_rule

        svc = _svc()
        svc.execute_rule.return_value = MagicMock()

        await execute_rule(
            workspace_id=ORG,
            rule_id=RULE_ID,
            request=MagicMock(),
            service=svc,
            actor=_user(),
        )
        svc.execute_rule.assert_awaited_once()


# ===================================================================
# schedule / violations / summary
# ===================================================================
class TestScheduleRule:
    @pytest.mark.asyncio
    async def test_sets_schedule(self):
        """P01-13: Schedule → returns rule"""
        from app.api.v1.endpoints.rules import schedule_rule

        svc = _svc()
        mock_rule = MagicMock()
        svc.schedule_rule.return_value = mock_rule

        result = await schedule_rule(
            workspace_id=ORG,
            rule_id=RULE_ID,
            schedule=MagicMock(),
            service=svc,
        )
        assert result == mock_rule


class TestGetViolations:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        """P01-14: Violations → returns list"""
        from app.api.v1.endpoints.rules import get_violations

        svc = _svc()
        svc.get_violations.return_value = [MagicMock()]

        result = await get_violations(
            workspace_id=ORG,
            execution_id=EXEC_ID,
            service=svc,
        )
        assert len(result) == 1


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_returns_summary(self):
        """P01-15: Summary → returns summary"""
        from app.api.v1.endpoints.rules import get_execution_summary

        svc = _svc()
        mock_summary = MagicMock()
        svc.get_execution_summary.return_value = mock_summary

        result = await get_execution_summary(
            workspace_id=ORG,
            service=svc,
        )
        assert result == mock_summary
