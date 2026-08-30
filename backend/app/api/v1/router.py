"""
API Router - Main router including all endpoints
"""

from fastapi import APIRouter

from app.api.v1 import spark
from app.api.v1.endpoints import (
    admin_demo_requests,
    admin_demo_templates,
    admin_sandboxes,
    alert_channels,
    alerts,
    anomalies,
    api_entities,
    api_write_entities,
    audit_logs,
    auth,
    connector_catalog,
    datasets,
    datasources,
    demo_requests,
    domains,
    escalation,
    executions,
    flows,
    glossary,
    incidents,
    ingestion,
    issue_incident_reports,
    issues,
    kqi,
    metadata,
    metadata_connectors,
    notification_events,
    ownership_history,
    permission_audit,
    platform_celery,
    proposal,
    provisioning,
    rbac,
    reporting,
    rule_builder,
    rule_templates,
    rules,
    sandbox_user,
    teams,
    tenant_connections,
    tenant_glossary,
    tenant_invitations,
    tenant_members,
    tenant_settings,
    tenants,
    ticketing,
    tokens,
    webhooks,
    workspace_data_sources,
    workspace_demo_data,
    workspace_roles,
    workspaces,
)

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(tokens.router, tags=["tokens"])
api_router.include_router(domains.router)
api_router.include_router(teams.router)
api_router.include_router(rbac.router)
api_router.include_router(rbac.global_router)  # Global RBAC endpoints (permissions)
api_router.include_router(datasources.router)  # Data Sources
api_router.include_router(ingestion.router)  # Data Ingestion
api_router.include_router(
    rules.router, tags=["rules"]
)  # Rule Management (paths include /organizations/{id})
api_router.include_router(flows.router)  # Flow Builder
api_router.include_router(flows.execution_router)  # Flow Executions
api_router.include_router(reporting.router)  # Reporting & Metrics
api_router.include_router(
    spark.router, prefix="/monitoring", tags=["spark-monitoring"]
)  # Spark monitoring
api_router.include_router(tenants.router)  # F001 — Tenant lifecycle
api_router.include_router(workspaces.router)  # F002 — Workspace creation and archival
api_router.include_router(workspace_demo_data.router)  # D4 — Workspace demo data bootstrap
api_router.include_router(workspace_data_sources.router)  # F004 — Data Source Connection Management
api_router.include_router(datasets.router)  # F005 — Dataset Registration and Schema
api_router.include_router(workspace_roles.router)  # F007 — Workspace Role Management
api_router.include_router(issues.router)  # F031 — Automatic Issue Creation
api_router.include_router(incidents.router)  # F038 — Manual Incident Creation
api_router.include_router(permission_audit.router)  # F008 — Permission Audit Visibility
api_router.include_router(alerts.router)  # F043 — Alert Rule Configuration
api_router.include_router(alert_channels.router)  # F044 — Alert Channel and Recipient Targeting
api_router.include_router(notification_events.router)  # F045 — Notification Event Logging
api_router.include_router(anomalies.router)  # F5 — Persisted Anomaly Detections
api_router.include_router(platform_celery.router)  # F6 — Celery / Flower observability
api_router.include_router(issue_incident_reports.router)  # F050 — Issue and Incident Reporting
api_router.include_router(audit_logs.router)  # F053 — Audit Log Search and Filtering
api_router.include_router(api_entities.router)  # F057 — Read APIs for Core Entities (token auth)
api_router.include_router(escalation.router)  # F046 — Escalation for Overdue SLA
api_router.include_router(
    ownership_history.router
)  # F055 — Ownership History and Accountability Trace
api_router.include_router(
    api_write_entities.router
)  # F058 — Write APIs for Selected Workflows (token auth)
api_router.include_router(webhooks.router)  # F059 — Webhook and Event Delivery
api_router.include_router(ticketing.router)  # F060 — External Ticketing Integration Hooks
api_router.include_router(rule_templates.router)  # F093 — DQ Dimension Template Library
api_router.include_router(kqi.router)  # F095 — KQI Dynamic Reports Engine
api_router.include_router(provisioning.router)  # Tenant Provisioning — automated setup
api_router.include_router(rule_builder.router)  # F099 — NL Rule Builder Parsing Service
api_router.include_router(metadata.router)  # F101 — Metadata Search Abstraction Layer
api_router.include_router(metadata_connectors.router)  # F108 — Metadata Connectors Framework
api_router.include_router(glossary.router)  # F109 — Business Glossary Management
api_router.include_router(proposal.router)  # F111 — Unified Proposal Engine
api_router.include_router(executions.router)  # F118 — Execution Storage & History
api_router.include_router(tenant_connections.router)  # F130 — Tenant-scoped Connection Management
api_router.include_router(connector_catalog.router)  # F-CONN-CORE — Connector Registry / Catalog
api_router.include_router(tenant_glossary.router)  # F130 — Tenant-scoped Glossary
api_router.include_router(tenant_invitations.router)  # GAP-004 — Tenant invitation workflow
api_router.include_router(tenant_members.router)  # Tenant admin — member/assignment matrix
api_router.include_router(tenant_settings.router)  # Tenant admin — SMTP / external service config
api_router.include_router(demo_requests.router)  # F134 — Demo Sandbox public intake
api_router.include_router(admin_demo_requests.router)  # F134 — Demo Sandbox admin review queue
api_router.include_router(admin_demo_templates.router)  # F134 — Demo Template registry
api_router.include_router(admin_sandboxes.router)  # F134 — Admin sandbox management
api_router.include_router(sandbox_user.router)  # F134 — Sandbox user endpoints
