"""
KQI (Key Quality Indicator) API endpoints.

12 endpoints serving dynamic KQI metrics across 5 report views.
"""

import logging
import uuid as _uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.models.database import get_db
from app.models.user import User
from app.schemas.kqi import (
    BusinessValueSummaryResponse,
    CheckHeatmapResponse,
    CheckIntelligenceSummaryResponse,
    CheckInventoryResponse,
    CostModelEntry,
    CostModelResponse,
    CostModelUpdateRequest,
    CoverageInventoryResponse,
    CoverageTrendResponse,
    DatasetProfileResponse,
    GovernanceMaturityResponse,
    OperationalSummaryResponse,
    OperationalTimelineResponse,
    ProblematicChecksResponse,
    RecentAlertsResponse,
    TopFlowsResponse,
)
from app.services.auth.jwt import get_current_user
from app.services.kqi.anomaly_detection_service import AnomalyDetectionService
from app.services.kqi.business_value_service import BusinessValueService
from app.services.kqi.check_effectiveness_service import CheckEffectivenessService
from app.services.kqi.coverage_service import CoverageService
from app.services.kqi.dataset_quality_service import DatasetQualityService
from app.services.kqi.incident_sla_service import IncidentSLAService
from app.services.kqi.operational_intelligence_service import OperationalIntelligenceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["kqi"])


async def verify_org_access(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return None


# =====================================================================
# Coverage Report  (KQI-001 to KQI-019)
# =====================================================================


@router.get("/kqi/coverage/inventory", response_model=CoverageInventoryResponse)
async def get_coverage_inventory(
    workspace_id: UUID,
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-001 to KQI-010: Dataset and flow inventory metrics."""
    try:
        svc = CoverageService(db)
        return svc.get_inventory(workspace_id, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get coverage inventory: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/coverage/checks", response_model=CheckInventoryResponse)
async def get_check_inventory(
    workspace_id: UUID,
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-011 to KQI-013: Check inventory by dimension and type."""
    try:
        svc = CoverageService(db)
        return svc.get_check_inventory(workspace_id, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get check inventory: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/coverage/maturity", response_model=GovernanceMaturityResponse)
async def get_governance_maturity(
    workspace_id: UUID,
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-014 to KQI-018: Governance maturity indicators."""
    try:
        svc = CoverageService(db)
        return svc.get_governance_maturity(workspace_id, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get governance maturity: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/coverage/trend", response_model=CoverageTrendResponse)
async def get_coverage_trend(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-019: Coverage trend over time."""
    try:
        svc = CoverageService(db)
        return svc.get_coverage_trend(workspace_id, period=period)
    except Exception as e:
        logger.error("Failed to get coverage trend: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =====================================================================
# Operational Intelligence Report  (KQI-026 to KQI-030)
# =====================================================================


@router.get("/kqi/operational/summary", response_model=OperationalSummaryResponse)
async def get_operational_summary(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-026 to KQI-030: Operational intelligence summary."""
    try:
        svc = OperationalIntelligenceService(db)
        return svc.get_summary(workspace_id, period=period, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get operational summary: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/operational/timeline", response_model=OperationalTimelineResponse)
async def get_operational_timeline(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-026 timeline: Daily execution success/partial/failed counts."""
    try:
        svc = OperationalIntelligenceService(db)
        return svc.get_timeline(workspace_id, period=period)
    except Exception as e:
        logger.error("Failed to get operational timeline: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/operational/check-heatmap", response_model=CheckHeatmapResponse)
async def get_check_heatmap(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Check performance heatmap: pass rate per check per day."""
    try:
        svc = OperationalIntelligenceService(db)
        return svc.get_check_heatmap(workspace_id, period=period)
    except Exception as e:
        logger.error("Failed to get check heatmap: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/operational/recent-alerts", response_model=RecentAlertsResponse)
async def get_recent_alerts(
    workspace_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Recent alerts from failed/warning check executions."""
    try:
        svc = OperationalIntelligenceService(db)
        return svc.get_recent_alerts(workspace_id, limit=limit)
    except Exception as e:
        logger.error("Failed to get recent alerts: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =====================================================================
# Dataset Quality Report  (KQI-031 to KQI-040)
# =====================================================================


@router.get("/kqi/datasets/{dataset_id}/profile", response_model=DatasetProfileResponse)
async def get_dataset_profile(
    workspace_id: UUID,
    dataset_id: str,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-031 to KQI-040: Per-dataset quality profile."""
    try:
        svc = DatasetQualityService(db)
        return svc.get_profile(
            workspace_id, dataset_id=dataset_id, period=period, use_cache=use_cache
        )
    except Exception as e:
        logger.error("Failed to get dataset profile: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =====================================================================
# Check Intelligence Report  (KQI-041 to KQI-046)
# =====================================================================


@router.get("/kqi/checks/intelligence", response_model=CheckIntelligenceSummaryResponse)
async def get_check_intelligence(
    workspace_id: UUID,
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-041 to KQI-046: Check effectiveness summary and health distribution."""
    try:
        svc = CheckEffectivenessService(db)
        return svc.get_summary(workspace_id, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get check intelligence: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/checks/problematic", response_model=ProblematicChecksResponse)
async def get_problematic_checks(
    workspace_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Paginated list of noisy, always-pass, always-fail, and duplicate checks."""
    try:
        svc = CheckEffectivenessService(db)
        return svc.get_problematic_checks(workspace_id, page=page, page_size=page_size)
    except Exception as e:
        logger.error("Failed to get problematic checks: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =====================================================================
# Business Value Report  (KQI-064 to KQI-066)
# =====================================================================


@router.get("/kqi/value/summary", response_model=BusinessValueSummaryResponse)
async def get_business_value_summary(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """KQI-064 to KQI-066: Issues caught, incidents avoided, cost saved."""
    try:
        svc = BusinessValueService(db)
        return svc.get_summary(workspace_id, period=period, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get business value summary: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/value/top-flows", response_model=TopFlowsResponse)
async def get_top_flows(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Top flows ranked by business value (issues × severity)."""
    try:
        svc = BusinessValueService(db)
        return svc.get_top_flows(workspace_id, period=period, limit=limit)
    except Exception as e:
        logger.error("Failed to get top flows: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =====================================================================
# Incident SLA Analytics  (F096)
# =====================================================================


@router.get("/kqi/incident-sla/metrics")
async def get_incident_sla_metrics(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """SLA compliance rate, breach count, avg breach duration, MTTR."""
    try:
        period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = IncidentSLAService(db)
        return svc.get_metrics(workspace_id, period_days=period_days, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get incident SLA metrics: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/incident-sla/breaches")
async def get_incident_sla_breaches(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Breach distribution grouped by severity level."""
    try:
        period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = IncidentSLAService(db)
        return svc.get_breaches_by_severity(
            workspace_id, period_days=period_days, use_cache=use_cache
        )
    except Exception as e:
        logger.error("Failed to get incident SLA breaches: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/incident-sla/compliance-trend")
async def get_incident_sla_compliance_trend(
    workspace_id: UUID,
    weeks: int = Query(8, ge=2, le=52),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Weekly SLA compliance rate and breach count over time."""
    try:
        svc = IncidentSLAService(db)
        return svc.get_compliance_trend(workspace_id, weeks=weeks, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get incident SLA compliance trend: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/incident-sla/incidents")
async def get_incidents_with_sla(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Paginated incident list enriched with SLA target and elapsed time."""
    try:
        period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = IncidentSLAService(db)
        return svc.get_incidents_with_sla(
            workspace_id,
            period_days=period_days,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error("Failed to get incidents with SLA: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ======================================================================
# Anomaly Detection (F098)
# ======================================================================


@router.get("/kqi/anomalies/summary")
async def get_anomaly_summary(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Summary metrics for detected anomalies."""
    try:
        period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = AnomalyDetectionService(db)
        return svc.get_anomaly_summary(workspace_id, period_days=period_days, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get anomaly summary: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/anomalies/detected")
async def get_detected_anomalies(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Detailed list of detected anomalies."""
    try:
        period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = AnomalyDetectionService(db)
        return svc.get_detected_anomalies(
            workspace_id, period_days=period_days, use_cache=use_cache
        )
    except Exception as e:
        logger.error("Failed to get detected anomalies: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/anomalies/volume-trend")
async def get_anomaly_volume_trend(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Daily execution volume trends for anomaly detection."""
    try:
        days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = AnomalyDetectionService(db)
        return svc.get_volume_trends(workspace_id, days=days, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get volume trends: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/kqi/anomalies/suggestions")
async def get_anomaly_suggestions(
    workspace_id: UUID,
    period: str = Query("30d", regex=r"^(7d|30d|90d)$"),
    use_cache: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _org=Depends(verify_org_access),
):
    """Actionable suggestions based on detected anomaly patterns."""
    try:
        period_days = {"7d": 7, "30d": 30, "90d": 90}[period]
        svc = AnomalyDetectionService(db)
        return svc.get_suggestions(workspace_id, period_days=period_days, use_cache=use_cache)
    except Exception as e:
        logger.error("Failed to get anomaly suggestions: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ======================================================================
# Cost Model Configuration  (KQI-066 support)
# ======================================================================


@router.get("/kqi/value/cost-model", response_model=CostModelResponse)
async def get_cost_model(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:read")),
):
    """
    Return the workspace cost model used for KQI-066 (Estimated Cost Saved).

    Returns custom values if configured, otherwise falls back to system defaults.
    Accessible by: workspace_administrator, data_engineer, data_steward.
    """
    from app.models.kqi import CostModel

    rows = db.query(CostModel).filter(CostModel.workspace_id == workspace_id).all()

    if rows:
        costs = [
            CostModelEntry(severity=r.severity, estimated_cost_usd=r.estimated_cost_usd)
            for r in rows
        ]
        return CostModelResponse(costs=costs, is_custom=True)

    # Return defaults
    costs = [
        CostModelEntry(severity=sev, estimated_cost_usd=cost)
        for sev, cost in CostModel.DEFAULT_COSTS.items()
    ]
    return CostModelResponse(costs=costs, is_custom=False)


@router.put("/kqi/value/cost-model", response_model=CostModelResponse, status_code=200)
async def update_cost_model(
    workspace_id: UUID,
    body: CostModelUpdateRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
):
    """
    Upsert the workspace cost model for KQI-066 (Estimated Cost Saved).

    Each entry specifies the estimated USD cost per issue of a given severity.
    Accepted severities: critical, major, minor, info.
    Only workspace_administrator has settings:write and can call this endpoint.
    """
    from app.models.kqi import CostModel

    try:
        for entry in body.costs:
            existing = (
                db.query(CostModel)
                .filter(
                    CostModel.workspace_id == workspace_id,
                    CostModel.severity == entry.severity,
                )
                .first()
            )
            if existing:
                existing.estimated_cost_usd = entry.estimated_cost_usd
            else:
                db.add(
                    CostModel(
                        id=_uuid.uuid4(),
                        workspace_id=workspace_id,
                        severity=entry.severity,
                        estimated_cost_usd=entry.estimated_cost_usd,
                    )
                )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to update cost model for workspace %s: %s", workspace_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update cost model."
        )

    rows = db.query(CostModel).filter(CostModel.workspace_id == workspace_id).all()
    costs = [
        CostModelEntry(severity=r.severity, estimated_cost_usd=r.estimated_cost_usd) for r in rows
    ]
    return CostModelResponse(costs=costs, is_custom=True)
