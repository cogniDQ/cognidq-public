"""
API endpoints for dashboards and reporting.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.reporting import (
    CategoryBreakdown,
    OverviewMetrics,
    Scorecard,
    SourceBreakdown,
    TrendMetrics,
)
from app.services.auth.jwt import get_current_user
from app.services.reporting.metrics import MetricsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["reporting"])


async def verify_org_access(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify user has access to workspace (legacy: organization)."""
    # For now, just return - workspace access is checked by auth middleware
    return None


# ========== Metrics Endpoints ==========


@router.get("/metrics/overview", response_model=OverviewMetrics)
async def get_overview_metrics(
    workspace_id: UUID,
    use_cache: bool = True,
    flow_id: UUID = None,
    execution_id: UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get overall KPI metrics for organization or specific flow.

    Query Parameters:
        - flow_id: Optional - Get metrics for a specific flow only
        - execution_id: Optional - Get metrics for a specific execution only

    Returns:
        - Total rules
        - Total executions
        - Average pass rate
        - DQ score
        - Critical violations
        - Total data sources
        - Total flows
    """
    try:
        metrics_service = MetricsService(db)
        metrics = metrics_service.get_overview_metrics(
            workspace_id, use_cache=use_cache, flow_id=flow_id, execution_id=execution_id
        )
        return metrics
    except Exception as e:
        logger.error(f"Failed to get overview metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {str(e)}",
        )


@router.get("/metrics/trends", response_model=TrendMetrics)
async def get_trend_metrics(
    workspace_id: UUID,
    metric_name: str = "pass_rate",
    period: str = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get time series trend data.

    Args:
        - metric_name: pass_rate, execution_count, dq_score
        - period: 7d, 30d, 90d, 1y, all

    Returns:
        Time series data points for the specified metric
    """
    valid_metrics = ["pass_rate", "execution_count", "dq_score"]
    if metric_name not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metric_name. Must be one of: {', '.join(valid_metrics)}",
        )

    try:
        metrics_service = MetricsService(db)
        trends = metrics_service.get_trend_metrics(workspace_id, metric_name, period)
        return trends
    except Exception as e:
        logger.error(f"Failed to get trend metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve trends: {str(e)}",
        )


@router.get("/metrics/by-category", response_model=CategoryBreakdown)
async def get_category_breakdown(
    workspace_id: UUID,
    period: str = "30d",
    flow_id: UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get metrics breakdown by data quality category.

    Query Parameters:
        - period: 7d, 30d, 90d, 1y, all
        - flow_id: Optional - Get metrics for a specific flow only

    Returns:
        Metrics for each DQ category (completeness, validity, uniqueness, etc.)
    """
    try:
        metrics_service = MetricsService(db)
        breakdown = metrics_service.get_category_breakdown(workspace_id, period, flow_id=flow_id)
        return breakdown
    except Exception as e:
        logger.error(f"Failed to get category breakdown: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve category breakdown: {str(e)}",
        )


@router.get("/metrics/by-source", response_model=SourceBreakdown)
async def get_source_breakdown(
    workspace_id: UUID,
    period: str = "30d",
    flow_id: UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get metrics breakdown by data source.

    Query Parameters:
        - period: 7d, 30d, 90d, 1y, all
        - flow_id: Optional - Get metrics for a specific flow only

    Returns:
        Metrics for each data source with health status
    """
    try:
        metrics_service = MetricsService(db)
        breakdown = metrics_service.get_source_breakdown(workspace_id, period, flow_id=flow_id)
        return breakdown
    except Exception as e:
        logger.error(f"Failed to get source breakdown: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve source breakdown: {str(e)}",
        )


@router.get("/metrics/scorecard", response_model=Scorecard)
async def get_scorecard(
    workspace_id: UUID,
    period: str = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get data quality scorecard with dimensional breakdown.

    Args:
        - period: 7d, 30d, 90d, 1y, all

    Returns:
        Overall DQ score and breakdown by dimension
    """
    try:
        metrics_service = MetricsService(db)
        scorecard = metrics_service.get_scorecard(workspace_id, period)
        return scorecard
    except Exception as e:
        logger.error(f"Failed to get scorecard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scorecard: {str(e)}",
        )


@router.get("/metrics/by-column")
async def get_column_metrics(
    workspace_id: UUID,
    flow_id: UUID = None,
    execution_id: UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get metrics breakdown by column.

    Query Parameters:
        - flow_id: Optional - Get metrics for a specific flow only
        - execution_id: Optional - Get metrics for a specific execution only

    Returns:
        List of columns with their check counts, pass rates, and status
    """
    try:
        logger.info(
            f"ðŸ“Š Column metrics requested: org={workspace_id}, flow={flow_id}, execution={execution_id}"
        )
        metrics_service = MetricsService(db)
        column_metrics = metrics_service.get_column_metrics(
            workspace_id, flow_id=flow_id, execution_id=execution_id
        )
        logger.info(f"ðŸ“Š Returning {len(column_metrics)} column metrics")
        return {"columns": column_metrics}
    except Exception as e:
        logger.error(f"Failed to get column metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve column metrics: {str(e)}",
        )


@router.get("/metrics/by-dimension")
async def get_dimensional_breakdown(
    workspace_id: UUID,
    flow_id: UUID = None,
    execution_id: UUID = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """
    Get metrics breakdown by dimension type (structural, semantic, statistical).

    Query Parameters:
        - flow_id: Optional - Get metrics for a specific flow only
        - execution_id: Optional - Get metrics for a specific execution only

    Returns:
        Metrics grouped by dimension category and check type
    """
    try:
        logger.info(
            f"ðŸ“Š Dimensional breakdown requested: org={workspace_id}, flow={flow_id}, execution={execution_id}"
        )
        metrics_service = MetricsService(db)
        breakdown = metrics_service.get_dimensional_breakdown(
            workspace_id, flow_id=flow_id, execution_id=execution_id
        )
        return breakdown
    except Exception as e:
        logger.error(f"Failed to get dimensional breakdown: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve dimensional breakdown: {str(e)}",
        )
