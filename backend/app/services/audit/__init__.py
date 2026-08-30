"""
F052 Audit Service Package
==========================

Public API::

    from app.services.audit import (
        AuditEntry,
        AuditContext,
        AuditService,
        AuditWriteFailedError,
        compute_audit_diff,
        strip_sensitive_fields,
        VALID_ACTION_TYPES,
        VALID_ENTITY_TYPES,
        SENSITIVE_FIELDS,
    )

    # Entity hook helpers
    from app.services.audit.hooks import build_rule_audit_entry, ...
"""

from app.services.audit.constants import (
    SENSITIVE_FIELDS,
    VALID_ACTION_TYPES,
    VALID_ENTITY_TYPES,
)
from app.services.audit.models import (
    AuditContext,
    AuditEntry,
    compute_audit_diff,
    strip_sensitive_fields,
)
from app.services.audit.service import AuditService, AuditWriteFailedError

__all__ = [
    "AuditContext",
    "AuditEntry",
    "AuditService",
    "AuditWriteFailedError",
    "compute_audit_diff",
    "strip_sensitive_fields",
    "SENSITIVE_FIELDS",
    "VALID_ACTION_TYPES",
    "VALID_ENTITY_TYPES",
]
