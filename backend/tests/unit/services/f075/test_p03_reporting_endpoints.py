"""
F075-P03  Reporting Endpoint Tests
15 tests · reporting.py endpoints + verify_org_access helper
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

REPORT_EP = "app.api.v1.endpoints.reporting"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _org():
    o = MagicMock()
    o.id = uuid4()
    return o


def _db():
    return MagicMock()


def _user():
    u = MagicMock()
    u.id = uuid4()
    return u


ORG_ID = uuid4()

# ---------------------------------------------------------------------------
# Import endpoint functions
# ---------------------------------------------------------------------------
from app.api.v1.endpoints.reporting import (
    get_category_breakdown,
    get_column_metrics,
    get_dimensional_breakdown,
    get_overview_metrics,
    get_scorecard,
    get_source_breakdown,
    get_trend_metrics,
    verify_org_access,
)


# ===========================================================================
# TestOverviewMetrics
# ===========================================================================
class TestOverviewMetrics:
    @pytest.mark.asyncio
    async def test_returns_metrics(self):
        mock_metrics = {"total_rules": 10, "pass_rate": 95.0}
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_overview_metrics.return_value = mock_metrics
            result = await get_overview_metrics(
                workspace_id=ORG_ID,
                use_cache=True,
                flow_id=None,
                execution_id=None,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_with_flow_filter(self):
        fid = uuid4()
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_overview_metrics.return_value = {}
            await get_overview_metrics(
                workspace_id=ORG_ID,
                use_cache=False,
                flow_id=fid,
                execution_id=None,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
            MockCls.return_value.get_overview_metrics.assert_called_once_with(
                ORG_ID,
                use_cache=False,
                flow_id=fid,
                execution_id=None,
            )

    @pytest.mark.asyncio
    async def test_error_500(self):
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_overview_metrics.side_effect = RuntimeError("boom")
            with pytest.raises(HTTPException) as exc:
                await get_overview_metrics(
                    workspace_id=ORG_ID,
                    use_cache=True,
                    flow_id=None,
                    execution_id=None,
                    db=_db(),
                    current_user=_user(),
                    _org=_org(),
                )
            assert exc.value.status_code == 500


# ===========================================================================
# TestTrendMetrics
# ===========================================================================
class TestTrendMetrics:
    @pytest.mark.asyncio
    async def test_returns_trends(self):
        data = {"data_points": [1, 2, 3]}
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_trend_metrics.return_value = data
            result = await get_trend_metrics(
                workspace_id=ORG_ID,
                metric_name="pass_rate",
                period="30d",
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == data

    @pytest.mark.asyncio
    async def test_invalid_metric_name_400(self):
        with pytest.raises(HTTPException) as exc:
            await get_trend_metrics(
                workspace_id=ORG_ID,
                metric_name="invalid_metric",
                period="7d",
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert exc.value.status_code == 400


# ===========================================================================
# TestCategoryBreakdown
# ===========================================================================
class TestCategoryBreakdown:
    @pytest.mark.asyncio
    async def test_returns_breakdown(self):
        data = {"completeness": 90}
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_category_breakdown.return_value = data
            result = await get_category_breakdown(
                workspace_id=ORG_ID,
                period="30d",
                flow_id=None,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == data

    @pytest.mark.asyncio
    async def test_error_500(self):
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_category_breakdown.side_effect = Exception("fail")
            with pytest.raises(HTTPException) as exc:
                await get_category_breakdown(
                    workspace_id=ORG_ID,
                    period="30d",
                    flow_id=None,
                    db=_db(),
                    current_user=_user(),
                    _org=_org(),
                )
            assert exc.value.status_code == 500


# ===========================================================================
# TestSourceBreakdown
# ===========================================================================
class TestSourceBreakdown:
    @pytest.mark.asyncio
    async def test_returns_breakdown(self):
        data = {"sources": [{"name": "orders"}]}
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_source_breakdown.return_value = data
            result = await get_source_breakdown(
                workspace_id=ORG_ID,
                period="30d",
                flow_id=None,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == data


# ===========================================================================
# TestScorecard
# ===========================================================================
class TestScorecard:
    @pytest.mark.asyncio
    async def test_returns_scorecard(self):
        data = {"overall_score": 87.5}
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_scorecard.return_value = data
            result = await get_scorecard(
                workspace_id=ORG_ID,
                period="30d",
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == data

    @pytest.mark.asyncio
    async def test_error_500(self):
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_scorecard.side_effect = Exception("err")
            with pytest.raises(HTTPException) as exc:
                await get_scorecard(
                    workspace_id=ORG_ID,
                    period="30d",
                    db=_db(),
                    current_user=_user(),
                    _org=_org(),
                )
            assert exc.value.status_code == 500


# ===========================================================================
# TestColumnMetrics
# ===========================================================================
class TestColumnMetrics:
    @pytest.mark.asyncio
    async def test_returns_columns(self):
        col_data = [{"column": "email", "pass_rate": 99}]
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_column_metrics.return_value = col_data
            result = await get_column_metrics(
                workspace_id=ORG_ID,
                flow_id=None,
                execution_id=None,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == {"columns": col_data}

    @pytest.mark.asyncio
    async def test_with_execution_filter(self):
        eid = uuid4()
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_column_metrics.return_value = []
            await get_column_metrics(
                workspace_id=ORG_ID,
                flow_id=None,
                execution_id=eid,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
            MockCls.return_value.get_column_metrics.assert_called_once_with(
                ORG_ID,
                flow_id=None,
                execution_id=eid,
            )


# ===========================================================================
# TestDimensionalBreakdown
# ===========================================================================
class TestDimensionalBreakdown:
    @pytest.mark.asyncio
    async def test_returns_breakdown(self):
        data = {"structural": {"pass_rate": 92}}
        with patch(f"{REPORT_EP}.MetricsService") as MockCls:
            MockCls.return_value.get_dimensional_breakdown.return_value = data
            result = await get_dimensional_breakdown(
                workspace_id=ORG_ID,
                flow_id=None,
                execution_id=None,
                db=_db(),
                current_user=_user(),
                _org=_org(),
            )
        assert result == data


# ===========================================================================
# TestVerifyOrgAccess
# ===========================================================================
class TestVerifyOrgAccess:
    @pytest.mark.asyncio
    async def test_org_exists(self):
        db = _db()
        result = await verify_org_access(
            workspace_id=ORG_ID,
            db=db,
            current_user=_user(),
        )
        # verify_org_access now always returns None (workspace auth delegated to middleware)
        assert result is None

    @pytest.mark.asyncio
    async def test_org_not_found_404(self):
        # verify_org_access no longer raises 404 — it is a no-op that returns None.
        db = _db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = await verify_org_access(
            workspace_id=ORG_ID,
            db=db,
            current_user=_user(),
        )
        assert result is None
