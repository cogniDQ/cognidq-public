"""
F075-P02 · Flow Endpoint Tests
15 tests — covers create, list, get, update, delete, validate, execute,
duplicate, export, import, execution_history endpoints.

Directly calls async endpoint functions with patched global flow_service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

FLOW_EP = "app.api.v1.endpoints.flows"

ORG = uuid4()
FLOW_ID = uuid4()


def _user():
    u = MagicMock()
    u.id = uuid4()
    u.tenant_id = uuid4()
    u.platform_role = "admin"
    return u


def _db():
    return MagicMock()


# ===================================================================
# create_flow
# ===================================================================
class TestCreateFlow:
    @pytest.mark.asyncio
    async def test_returns_201(self):
        """P02-01: Successful create → returns flow"""
        from app.api.v1.endpoints.flows import create_flow

        mock_flow = MagicMock()
        mock_flow.id = uuid4()
        mock_flow.name = "test"
        mock_flow.status = "draft"

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.create_flow.return_value = mock_flow
            result = await create_flow(
                workspace_id=ORG,
                request=MagicMock(),
                db=_db(),
                actor=_user(),
            )
        assert result == mock_flow

    @pytest.mark.asyncio
    async def test_validation_error_400(self):
        """P02-02: ValueError → HTTPException 400"""
        from app.api.v1.endpoints.flows import create_flow

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.create_flow.side_effect = ValueError("bad")
            with pytest.raises(HTTPException) as exc_info:
                await create_flow(
                    workspace_id=ORG,
                    request=MagicMock(),
                    db=_db(),
                    actor=_user(),
                )
        assert exc_info.value.status_code == 400


# ===================================================================
# list_flows
# ===================================================================
class TestListFlows:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        """P02-03: List flows → returns list response"""
        from app.api.v1.endpoints.flows import list_flows

        mock_result = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.list_flows.return_value = mock_result
            result = await list_flows(
                workspace_id=ORG,
                db=_db(),
                actor=_user(),
            )
        assert result == mock_result


# ===================================================================
# get_flow
# ===================================================================
class TestGetFlow:
    @pytest.mark.asyncio
    async def test_found(self):
        """P02-04: Existing flow → returns flow"""
        from app.api.v1.endpoints.flows import get_flow

        mock_flow = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.get_flow.return_value = mock_flow
            result = await get_flow(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                db=_db(),
                actor=_user(),
            )
        assert result == mock_flow

    @pytest.mark.asyncio
    async def test_not_found_404(self):
        """P02-05: Missing flow → HTTPException 404"""
        from app.api.v1.endpoints.flows import get_flow

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.get_flow.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_flow(
                    workspace_id=ORG,
                    flow_id=FLOW_ID,
                    db=_db(),
                    actor=_user(),
                )
        assert exc_info.value.status_code == 404


# ===================================================================
# update_flow / delete_flow
# ===================================================================
class TestUpdateFlow:
    @pytest.mark.asyncio
    async def test_returns_updated(self):
        """P02-06: Update → returns updated flow"""
        from app.api.v1.endpoints.flows import update_flow

        mock_flow = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.update_flow.return_value = mock_flow
            result = await update_flow(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                request=MagicMock(),
                db=_db(),
                actor=_user(),
            )
        assert result == mock_flow


class TestDeleteFlow:
    @pytest.mark.asyncio
    async def test_returns_none(self):
        """P02-07: Delete → no exception raised"""
        from app.api.v1.endpoints.flows import delete_flow

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.delete_flow.return_value = True
            # should not raise
            await delete_flow(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                db=_db(),
                actor=_user(),
            )


# ===================================================================
# validate_flow
# ===================================================================
class TestValidateFlow:
    @pytest.mark.asyncio
    async def test_valid(self):
        """P02-08: Validate → returns validation result"""
        from app.api.v1.endpoints.flows import validate_flow

        mock_result = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.validator.validate_flow.return_value = mock_result
            result = await validate_flow(
                workspace_id=ORG,
                request=MagicMock(),
                db=_db(),
                actor=_user(),
            )
        assert result == mock_result


# ===================================================================
# execute_flow
# ===================================================================
class TestExecuteFlow:
    @pytest.mark.asyncio
    async def test_returns_execution(self):
        """P02-09: Execute → returns execution response"""
        from app.api.v1.endpoints.flows import execute_flow

        mock_exec = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.execute_flow_async = AsyncMock(return_value=mock_exec)
            result = await execute_flow(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                background_tasks=BackgroundTasks(),
                db=_db(),
                actor=_user(),
            )
        assert result == mock_exec

    @pytest.mark.asyncio
    async def test_error_500(self):
        """P02-10: Generic exception → HTTPException 500"""
        from app.api.v1.endpoints.flows import execute_flow

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.execute_flow_async = AsyncMock(side_effect=RuntimeError("boom"))
            with pytest.raises(HTTPException) as exc_info:
                await execute_flow(
                    workspace_id=ORG,
                    flow_id=FLOW_ID,
                    background_tasks=BackgroundTasks(),
                    db=_db(),
                    actor=_user(),
                )
        assert exc_info.value.status_code == 500


# ===================================================================
# duplicate_flow
# ===================================================================
class TestDuplicateFlow:
    @pytest.mark.asyncio
    async def test_returns_duplicate(self):
        """P02-11: Duplicate → returns new flow"""
        from app.api.v1.endpoints.flows import duplicate_flow

        mock_flow = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.duplicate_flow.return_value = mock_flow
            result = await duplicate_flow(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                db=_db(),
                actor=_user(),
            )
        assert result == mock_flow


# ===================================================================
# export_flow
# ===================================================================
class TestExportFlow:
    @pytest.mark.asyncio
    async def test_returns_response(self):
        """P02-12: Export → returns Response with content-disposition"""
        from app.api.v1.endpoints.flows import export_flow

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.export_flow.return_value = '{"name": "test"}'
            result = await export_flow(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                db=_db(),
                actor=_user(),
            )
        assert result.status_code == 200
        assert "content-disposition" in result.headers


# ===================================================================
# import_flow
# ===================================================================
class TestImportFlow:
    @pytest.mark.asyncio
    async def test_returns_flow(self):
        """P02-13: Import → returns flow"""
        from app.api.v1.endpoints.flows import import_flow

        mock_flow = MagicMock()
        mock_request = MagicMock()
        mock_request.name = "imported"
        mock_request.description = "desc"
        mock_request.flow_definition.dict.return_value = {}
        mock_request.tags = []

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.import_flow.return_value = mock_flow
            result = await import_flow(
                workspace_id=ORG,
                request=mock_request,
                db=_db(),
                actor=_user(),
            )
        assert result == mock_flow


# ===================================================================
# execution_history
# ===================================================================
class TestExecutionHistory:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        """P02-14: Execution history → returns list"""
        from app.api.v1.endpoints.flows import get_execution_history

        mock_result = MagicMock()
        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.get_execution_history.return_value = mock_result
            result = await get_execution_history(
                workspace_id=ORG,
                flow_id=FLOW_ID,
                db=_db(),
                actor=_user(),
            )
        assert result == mock_result

    @pytest.mark.asyncio
    async def test_error_500(self):
        """P02-15: Exception → HTTPException 500"""
        from app.api.v1.endpoints.flows import get_execution_history

        with patch(f"{FLOW_EP}.flow_service") as mock_svc:
            mock_svc.get_execution_history.side_effect = RuntimeError("fail")
            with pytest.raises(HTTPException) as exc_info:
                await get_execution_history(
                    workspace_id=ORG,
                    flow_id=FLOW_ID,
                    db=_db(),
                    actor=_user(),
                )
        assert exc_info.value.status_code == 500
