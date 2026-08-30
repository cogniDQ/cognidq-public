"""
F043 P02 — AlertRuleService Tests
===================================

15 tests covering service-layer CRUD, validation, and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest
from app.models.alert_rule import AlertRule
from app.services.alerts.alert_rule_service import (
    AlertRuleLimitError,
    AlertRuleNotFoundError,
    AlertRuleService,
    AlertRuleValidationError,
    DuplicateAlertRuleNameError,
)
from app.services.audit.models import AuditContext

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_rule(**overrides) -> AlertRule:
    now = datetime.now(UTC)
    defaults = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        name="Exec failure alert",
        trigger_type="execution_failed",
        conditions=None,
        recipient_user_ids=[str(uuid4())],
        enabled=True,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return AlertRule(**defaults)


def _mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.name_exists.return_value = False
    repo.count_by_workspace.return_value = 0
    return repo


def _mock_audit() -> MagicMock:
    return MagicMock()


def _audit_ctx() -> AuditContext:
    return AuditContext(
        tenant_id=uuid4(),
        actor_id=uuid4(),
        actor_type="user",
        actor_role="admin",
        request_id=None,
        source_ip=None,
    )


def _svc(repo=None, audit=None) -> AlertRuleService:
    return AlertRuleService(
        repo=repo or _mock_repo(),
        audit_service=audit or _mock_audit(),
    )


# ── Create Tests ─────────────────────────────────────────────────────────────


class TestCreateRule:
    def test_create_rule_success(self):
        repo = _mock_repo()
        rule = _make_rule()
        repo.insert.return_value = rule
        svc = _svc(repo=repo)

        result = svc.create_rule(
            MagicMock(),
            workspace_id=rule.workspace_id,
            tenant_id=rule.tenant_id,
            created_by_user_id=rule.created_by_user_id,
            name=rule.name,
            trigger_type="execution_failed",
            recipient_user_ids=[str(uuid4())],
        )
        assert result.name == rule.name
        repo.insert.assert_called_once()

    def test_create_name_validation(self):
        svc = _svc()
        with pytest.raises(AlertRuleValidationError, match="name"):
            svc.create_rule(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="   ",
                trigger_type="execution_failed",
                recipient_user_ids=[str(uuid4())],
            )

    def test_create_invalid_trigger_type(self):
        svc = _svc()
        with pytest.raises(AlertRuleValidationError, match="trigger_type"):
            svc.create_rule(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="Test",
                trigger_type="unknown",
                recipient_user_ids=[str(uuid4())],
            )

    def test_create_empty_recipients(self):
        svc = _svc()
        with pytest.raises(AlertRuleValidationError, match="recipient"):
            svc.create_rule(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="Test",
                trigger_type="execution_failed",
                recipient_user_ids=[],
            )

    def test_create_duplicate_name(self):
        repo = _mock_repo()
        repo.name_exists.return_value = True
        svc = _svc(repo=repo)
        with pytest.raises(DuplicateAlertRuleNameError):
            svc.create_rule(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="Duplicate",
                trigger_type="execution_failed",
                recipient_user_ids=[str(uuid4())],
            )

    def test_create_limit_exceeded(self):
        repo = _mock_repo()
        repo.count_by_workspace.return_value = 50
        svc = _svc(repo=repo)
        with pytest.raises(AlertRuleLimitError):
            svc.create_rule(
                MagicMock(),
                workspace_id=uuid4(),
                tenant_id=uuid4(),
                created_by_user_id=uuid4(),
                name="Test",
                trigger_type="execution_failed",
                recipient_user_ids=[str(uuid4())],
            )

    def test_create_audit_written(self):
        repo = _mock_repo()
        audit = _mock_audit()
        rule = _make_rule()
        repo.insert.return_value = rule
        svc = _svc(repo=repo, audit=audit)

        svc.create_rule(
            MagicMock(),
            workspace_id=rule.workspace_id,
            tenant_id=rule.tenant_id,
            created_by_user_id=rule.created_by_user_id,
            name=rule.name,
            trigger_type="execution_failed",
            recipient_user_ids=[str(uuid4())],
            audit_ctx=_audit_ctx(),
        )
        audit.write.assert_called_once()
        entry = audit.write.call_args[0][1]
        assert entry.action_type == "alert_rule_created"


# ── Read Tests ───────────────────────────────────────────────────────────────


class TestReadRules:
    def test_get_rule_success(self):
        repo = _mock_repo()
        rule = _make_rule()
        repo.get_by_id_and_workspace.return_value = rule
        svc = _svc(repo=repo)
        result = svc.get_rule(MagicMock(), rule_id=rule.id, workspace_id=rule.workspace_id)
        assert result.id == rule.id

    def test_get_rule_not_found(self):
        repo = _mock_repo()
        repo.get_by_id_and_workspace.return_value = None
        svc = _svc(repo=repo)
        with pytest.raises(AlertRuleNotFoundError):
            svc.get_rule(MagicMock(), rule_id=uuid4(), workspace_id=uuid4())

    def test_list_rules(self):
        repo = _mock_repo()
        rules = [_make_rule(), _make_rule()]
        repo.list_by_workspace.return_value = rules
        svc = _svc(repo=repo)
        result = svc.list_rules(MagicMock(), workspace_id=uuid4())
        assert len(result) == 2


# ── Update Tests ─────────────────────────────────────────────────────────────


class TestUpdateRule:
    def test_update_rule_success(self):
        repo = _mock_repo()
        rule = _make_rule()
        repo.get_by_id_and_workspace.return_value = rule
        repo.update.return_value = rule
        svc = _svc(repo=repo)
        result = svc.update_rule(
            MagicMock(),
            rule_id=rule.id,
            workspace_id=rule.workspace_id,
            name="Updated Name",
        )
        assert result is not None
        repo.update.assert_called_once()

    def test_update_rule_not_found(self):
        repo = _mock_repo()
        repo.get_by_id_and_workspace.return_value = None
        svc = _svc(repo=repo)
        with pytest.raises(AlertRuleNotFoundError):
            svc.update_rule(MagicMock(), rule_id=uuid4(), workspace_id=uuid4(), name="X")

    def test_update_duplicate_name(self):
        repo = _mock_repo()
        rule = _make_rule()
        repo.get_by_id_and_workspace.return_value = rule
        repo.name_exists.return_value = True
        svc = _svc(repo=repo)
        with pytest.raises(DuplicateAlertRuleNameError):
            svc.update_rule(
                MagicMock(),
                rule_id=rule.id,
                workspace_id=rule.workspace_id,
                name="Taken",
            )


# ── Delete Tests ─────────────────────────────────────────────────────────────


class TestDeleteRule:
    def test_delete_rule_success(self):
        repo = _mock_repo()
        audit = _mock_audit()
        rule = _make_rule()
        repo.get_by_id_and_workspace.return_value = rule
        svc = _svc(repo=repo, audit=audit)
        svc.delete_rule(
            MagicMock(),
            rule_id=rule.id,
            workspace_id=rule.workspace_id,
            audit_ctx=_audit_ctx(),
        )
        repo.delete.assert_called_once()
        audit.write.assert_called_once()

    def test_delete_rule_not_found(self):
        repo = _mock_repo()
        repo.get_by_id_and_workspace.return_value = None
        svc = _svc(repo=repo)
        with pytest.raises(AlertRuleNotFoundError):
            svc.delete_rule(MagicMock(), rule_id=uuid4(), workspace_id=uuid4())
