"""
F043 P03 — Alert Rule API Endpoint Tests (15 tests)
=====================================================

Covers:
  - POST/GET/PATCH/DELETE /workspaces/{ws}/alert-rules
  - Error mapping (201/200/204/404/409/422)
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.alerts.alert_rule_models import AlertRuleResponse
from app.services.alerts.alert_rule_service import (
    AlertRuleLimitError,
    AlertRuleNotFoundError,
    AlertRuleValidationError,
    DuplicateAlertRuleNameError,
)

ALERTS_EP = "app.api.v1.endpoints.alerts"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_RULE_ID = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.user_id = _USER
    actor.role = "admin"
    return actor


def _mock_response(**overrides) -> AlertRuleResponse:
    now = datetime.now(UTC)
    defaults = dict(
        id=_RULE_ID,
        workspace_id=_WS,
        name="Exec failure alert",
        trigger_type="execution_failed",
        conditions=None,
        recipient_user_ids=[str(uuid4())],
        enabled=True,
        created_by_user_id=_USER,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return AlertRuleResponse(**defaults)


def _mock_body_create(**overrides):
    body = MagicMock()
    body.name = overrides.get("name", "Test Alert")
    body.trigger_type = overrides.get("trigger_type", "execution_failed")
    body.conditions = overrides.get("conditions", None)
    body.recipient_user_ids = overrides.get("recipient_user_ids", [uuid4()])
    body.enabled = overrides.get("enabled", True)
    return body


def _mock_body_update(**overrides):
    body = MagicMock()
    body.name = overrides.get("name", None)
    body.trigger_type = overrides.get("trigger_type", None)
    body.conditions = overrides.get("conditions", None)
    body.recipient_user_ids = overrides.get("recipient_user_ids", None)
    body.enabled = overrides.get("enabled", None)
    return body


# ---------------------------------------------------------------------------
# POST Tests
# ---------------------------------------------------------------------------


class TestCreateAlertRule:
    @pytest.mark.asyncio
    async def test_create_201(self):
        from app.api.v1.endpoints.alerts import create_alert_rule

        resp = _mock_response()
        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.create_rule.return_value = resp
            result = await create_alert_rule(
                workspace_id=_WS,
                body=_mock_body_create(),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_create_409_duplicate(self):
        from app.api.v1.endpoints.alerts import create_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.create_rule.side_effect = DuplicateAlertRuleNameError("dup")
            with pytest.raises(Exception) as exc_info:
                await create_alert_rule(
                    workspace_id=_WS,
                    body=_mock_body_create(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_422_validation(self):
        from app.api.v1.endpoints.alerts import create_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.create_rule.side_effect = AlertRuleValidationError("bad")
            with pytest.raises(Exception) as exc_info:
                await create_alert_rule(
                    workspace_id=_WS,
                    body=_mock_body_create(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_422_empty_recipients(self):
        from app.api.v1.endpoints.alerts import create_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.create_rule.side_effect = AlertRuleValidationError("recipient")
            with pytest.raises(Exception) as exc_info:
                await create_alert_rule(
                    workspace_id=_WS,
                    body=_mock_body_create(recipient_user_ids=[]),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_limit_exceeded_409(self):
        from app.api.v1.endpoints.alerts import create_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.create_rule.side_effect = AlertRuleLimitError("limit")
            with pytest.raises(Exception) as exc_info:
                await create_alert_rule(
                    workspace_id=_WS,
                    body=_mock_body_create(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_conditions_stored(self):
        from app.api.v1.endpoints.alerts import create_alert_rule

        conditions = {"severity_in": ["critical", "major"]}
        resp = _mock_response(conditions=conditions)
        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.create_rule.return_value = resp
            result = await create_alert_rule(
                workspace_id=_WS,
                body=_mock_body_create(conditions=conditions),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        import json

        body = json.loads(result.body)
        assert body["conditions"] == conditions


# ---------------------------------------------------------------------------
# GET Tests
# ---------------------------------------------------------------------------


class TestListAndGetAlertRules:
    @pytest.mark.asyncio
    async def test_list_200(self):
        from app.api.v1.endpoints.alerts import list_alert_rules

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.list_rules.return_value = [_mock_response(), _mock_response()]
            result = await list_alert_rules(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200
        import json

        body = json.loads(result.body)
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_get_200(self):
        from app.api.v1.endpoints.alerts import get_alert_rule

        resp = _mock_response()
        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.get_rule.return_value = resp
            result = await get_alert_rule(
                workspace_id=_WS,
                rule_id=_RULE_ID,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_404(self):
        from app.api.v1.endpoints.alerts import get_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.get_rule.side_effect = AlertRuleNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await get_alert_rule(
                    workspace_id=_WS,
                    rule_id=uuid4(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PATCH Tests
# ---------------------------------------------------------------------------


class TestUpdateAlertRule:
    @pytest.mark.asyncio
    async def test_patch_200(self):
        from app.api.v1.endpoints.alerts import update_alert_rule

        resp = _mock_response(name="Updated")
        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.update_rule.return_value = resp
            result = await update_alert_rule(
                workspace_id=_WS,
                rule_id=_RULE_ID,
                body=_mock_body_update(name="Updated"),
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_404(self):
        from app.api.v1.endpoints.alerts import update_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.update_rule.side_effect = AlertRuleNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await update_alert_rule(
                    workspace_id=_WS,
                    rule_id=uuid4(),
                    body=_mock_body_update(name="X"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_409_duplicate_name(self):
        from app.api.v1.endpoints.alerts import update_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.update_rule.side_effect = DuplicateAlertRuleNameError("dup")
            with pytest.raises(Exception) as exc_info:
                await update_alert_rule(
                    workspace_id=_WS,
                    rule_id=_RULE_ID,
                    body=_mock_body_update(name="Taken"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_patch_422(self):
        from app.api.v1.endpoints.alerts import update_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.update_rule.side_effect = AlertRuleValidationError("bad")
            with pytest.raises(Exception) as exc_info:
                await update_alert_rule(
                    workspace_id=_WS,
                    rule_id=_RULE_ID,
                    body=_mock_body_update(trigger_type="invalid"),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# DELETE Tests
# ---------------------------------------------------------------------------


class TestDeleteAlertRule:
    @pytest.mark.asyncio
    async def test_delete_204(self):
        from app.api.v1.endpoints.alerts import delete_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.delete_rule.return_value = None
            result = await delete_alert_rule(
                workspace_id=_WS,
                rule_id=_RULE_ID,
                actor=_mock_actor(),
                db=MagicMock(),
            )
        assert result.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_404(self):
        from app.api.v1.endpoints.alerts import delete_alert_rule

        with patch(f"{ALERTS_EP}._svc") as svc_mock:
            svc_mock.delete_rule.side_effect = AlertRuleNotFoundError("nf")
            with pytest.raises(Exception) as exc_info:
                await delete_alert_rule(
                    workspace_id=_WS,
                    rule_id=uuid4(),
                    actor=_mock_actor(),
                    db=MagicMock(),
                )
            assert exc_info.value.status_code == 404
