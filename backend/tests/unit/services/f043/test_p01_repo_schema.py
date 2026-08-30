"""
F043 P01 — ORM + Repository + Schema Tests
============================================

15 tests covering AlertRule ORM model, Pydantic schemas, and repository CRUD.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest
from app.models.alert_rule import AlertRule
from app.services.alerts.alert_rule_models import (
    VALID_TRIGGER_TYPES,
    AlertRuleResponse,
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
)
from app.services.alerts.alert_rule_repository import AlertRuleRepository

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_rule(**overrides) -> AlertRule:
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    rule = AlertRule(**defaults)
    return rule


def _mock_db() -> MagicMock:
    return MagicMock()


# ── ORM Tests ────────────────────────────────────────────────────────────────


class TestAlertRuleORM:
    def test_alert_rule_table_name(self):
        assert AlertRule.__tablename__ == "alert_rules"

    def test_alert_rule_columns(self):
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "name",
            "trigger_type",
            "conditions",
            "recipient_user_ids",
            "enabled",
            "created_by_user_id",
            "created_at",
            "updated_at",
        }
        cols = {c.name for c in AlertRule.__table__.columns}
        assert expected.issubset(cols)

    def test_alert_rule_defaults(self):
        AlertRule(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            name="test",
            trigger_type="issue_created",
            recipient_user_ids=[str(uuid4())],
        )
        # Column default=True is applied at flush time; at init it's the column default
        col_default = AlertRule.__table__.c.enabled.default.arg
        assert col_default is True
        # id default callable is set
        assert AlertRule.__table__.c.id.default is not None


# ── Schema Tests ─────────────────────────────────────────────────────────────


class TestPydanticSchemas:
    def test_create_request_valid(self):
        uid = uuid4()
        req = CreateAlertRuleRequest(
            name="Test Alert",
            trigger_type="execution_failed",
            recipient_user_ids=[uid],
        )
        assert req.name == "Test Alert"
        assert req.trigger_type == "execution_failed"
        assert req.enabled is True

    def test_create_request_name_blank(self):
        with pytest.raises(Exception):
            CreateAlertRuleRequest(
                name="   ",
                trigger_type="execution_failed",
                recipient_user_ids=[uuid4()],
            )

    def test_create_request_invalid_trigger(self):
        with pytest.raises(Exception):
            CreateAlertRuleRequest(
                name="Test",
                trigger_type="bad_trigger",
                recipient_user_ids=[uuid4()],
            )

    def test_create_request_empty_recipients(self):
        with pytest.raises(Exception):
            CreateAlertRuleRequest(
                name="Test",
                trigger_type="execution_failed",
                recipient_user_ids=[],
            )

    def test_update_request_all_optional(self):
        req = UpdateAlertRuleRequest()
        assert req.name is None
        assert req.trigger_type is None
        assert req.conditions is None
        assert req.recipient_user_ids is None
        assert req.enabled is None

    def test_response_model_fields(self):
        fields = set(AlertRuleResponse.model_fields.keys())
        expected = {
            "id",
            "workspace_id",
            "name",
            "trigger_type",
            "conditions",
            "recipient_user_ids",
            "enabled",
            "created_by_user_id",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(fields)


# ── Repository Tests ─────────────────────────────────────────────────────────


class TestAlertRuleRepository:
    def setup_method(self):
        self.repo = AlertRuleRepository()

    def test_repo_insert_calls_add_flush(self):
        db = _mock_db()
        rule = _make_rule()
        result = self.repo.insert(db, rule)
        db.add.assert_called_once_with(rule)
        db.flush.assert_called_once()
        assert result is rule

    def test_repo_get_by_id_and_workspace(self):
        db = _mock_db()
        rule_id, ws_id = uuid4(), uuid4()
        mock_query = db.query.return_value.filter.return_value
        mock_query.first.return_value = _make_rule(id=rule_id, workspace_id=ws_id)
        result = self.repo.get_by_id_and_workspace(db, rule_id, ws_id)
        assert result is not None
        db.query.assert_called_once_with(AlertRule)

    def test_repo_list_by_workspace(self):
        db = _mock_db()
        ws_id = uuid4()
        rules = [_make_rule(), _make_rule()]
        chain = db.query.return_value.filter.return_value.order_by.return_value
        chain.all.return_value = rules
        result = self.repo.list_by_workspace(db, ws_id)
        assert result == rules

    def test_repo_update_refreshes(self):
        db = _mock_db()
        rule = _make_rule()
        result = self.repo.update(db, rule)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(rule)
        assert result is rule

    def test_repo_delete_returns_bool(self):
        db = _mock_db()
        rule_id, ws_id = uuid4(), uuid4()
        # Simulate found
        rule = _make_rule(id=rule_id)
        with patch.object(self.repo, "get_by_id_and_workspace", return_value=rule):
            assert self.repo.delete(db, rule_id, ws_id) is True
            db.delete.assert_called_once_with(rule)
        # Simulate not found
        db.reset_mock()
        with patch.object(self.repo, "get_by_id_and_workspace", return_value=None):
            assert self.repo.delete(db, rule_id, ws_id) is False
            db.delete.assert_not_called()

    def test_repo_name_exists(self):
        db = _mock_db()
        ws_id = uuid4()
        chain = db.query.return_value.filter.return_value
        chain.first.return_value = (uuid4(),)
        assert self.repo.name_exists(db, ws_id, "Test") is True
        chain.first.return_value = None
        assert self.repo.name_exists(db, ws_id, "Unique") is False
