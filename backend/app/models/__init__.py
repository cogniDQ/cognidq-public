"""
Database models

Every model module must be imported here so SQLAlchemy can resolve
string-based relationship() targets regardless of which entry point
(API, worker, script) configures the mappers first.
"""

from .alert_channel import AlertChannel
from .alert_rule import AlertRule
from .audit_log import AuditLog
from .access_profile import AccessProfile  # noqa: F401
from .access_token import AccessToken  # noqa: F401 — required for User mapper config
from .dashboard import Dashboard  # noqa: F401
from .datasource import DataSource  # noqa: F401
from .demo_request import DemoRequest  # noqa: F401
from .demo_template import DemoTemplate  # noqa: F401
from .detected_anomaly import DetectedAnomaly
from .domain import Domain  # noqa: F401
from .flow import DQFlow, FlowExecution, FlowNodeResult  # noqa: F401
from .incident import Incident, IncidentIssue
from .issue import Issue
from .issue_comment import IssueComment
from .kqi import CostModel, KQISnapshot, SLADefinition
from .nl_rule import NLRuleParseResult, NLRuleRequest
from .notification_event import NotificationEvent  # noqa: F401
from .provisioning_job import ProvisioningJob  # noqa: F401
from .rbac import Permission, Role, UserRoleAssignment  # noqa: F401
from .rule import DQRule  # noqa: F401
from .sandbox_environment import SandboxEnvironment  # noqa: F401
from .sandbox_extension import SandboxExtension  # noqa: F401
from .sandbox_user import SandboxUser  # noqa: F401
from .team import Team  # noqa: F401 — required for User.teams mapper config
from .user import EmailVerification, MFASettings, PasswordReset, Session, User
from .webhook import WebhookSubscription  # noqa: F401

__all__ = [
    "User",
    "Session",
    "EmailVerification",
    "PasswordReset",
    "MFASettings",
    "Issue",
    "IssueComment",
    "Incident",
    "IncidentIssue",
    "AlertRule",
    "AlertChannel",
    "AuditLog",
    "SLADefinition",
    "CostModel",
    "KQISnapshot",
    "NLRuleRequest",
    "NLRuleParseResult",
    "DetectedAnomaly",
]
