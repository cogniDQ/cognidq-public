"""
F134 P02 — Domain Models, Repositories, Clock + Gate Interfaces — Unit Tests

Tests verify:
1. ORM model files exist and import without error
2. Python enum values match DB enum values from migration
3. Clock: SystemClock returns aware UTC; FrozenClock freezes + advances
4. Protocol conformance for SandboxFeatureGateProtocol, TemplateSeederProtocol
5. Repository classes exist and expose expected public methods
6. DemoRequestRepository.create / find_by_id / find_by_public_token / find_active_by_email / list_with_filters
7. SandboxEnvironmentRepository CRUD + list_expiring + list_ready_for_cleanup + increment_extension
8. SandboxUsageEventRepository insert / bulk_insert / summarise_by_sandbox / total_events
9. SandboxExtensionRepository create / count_by_sandbox / list_by_sandbox
10. ProvisioningJobRepository create / find_by_id / find_latest_for_request / update
11. DemoTemplateRepository find_by_id / list_enabled / list_all
12. AccessProfileRepository find_by_id / find_by_code / list_enabled
"""

from __future__ import annotations

import importlib
import inspect
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 1. Model imports
# ─────────────────────────────────────────────────────────────────────────────


class TestModelImports:
    def test_demo_template_imports(self):
        mod = importlib.import_module("app.models.demo_template")
        assert hasattr(mod, "DemoTemplate")

    def test_access_profile_imports(self):
        mod = importlib.import_module("app.models.access_profile")
        assert hasattr(mod, "AccessProfile")

    def test_demo_request_imports(self):
        mod = importlib.import_module("app.models.demo_request")
        assert hasattr(mod, "DemoRequest")
        assert hasattr(mod, "DemoRequestStatus")

    def test_sandbox_environment_imports(self):
        mod = importlib.import_module("app.models.sandbox_environment")
        assert hasattr(mod, "SandboxEnvironment")
        assert hasattr(mod, "SandboxEnvironmentStatus")

    def test_sandbox_user_imports(self):
        mod = importlib.import_module("app.models.sandbox_user")
        assert hasattr(mod, "SandboxUser")

    def test_sandbox_usage_event_imports(self):
        mod = importlib.import_module("app.models.sandbox_usage_event")
        assert hasattr(mod, "SandboxUsageEvent")
        assert hasattr(mod, "SandboxUsageEventType")

    def test_sandbox_extension_imports(self):
        mod = importlib.import_module("app.models.sandbox_extension")
        assert hasattr(mod, "SandboxExtension")

    def test_provisioning_job_imports(self):
        mod = importlib.import_module("app.models.provisioning_job")
        assert hasattr(mod, "ProvisioningJob")
        assert hasattr(mod, "ProvisioningJobStatus")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Enum values aligned with DB migration
# ─────────────────────────────────────────────────────────────────────────────


class TestEnumValues:
    def test_demo_request_status_values(self):
        from app.models.demo_request import DemoRequestStatus

        vals = {e.value for e in DemoRequestStatus}
        assert vals == {
            "submitted",
            "under_review",
            "approved",
            "rejected",
            "provisioned",
            "active",
            "expired",
            "archived",
            "converted",
        }

    def test_sandbox_environment_status_values(self):
        from app.models.sandbox_environment import SandboxEnvironmentStatus

        vals = {e.value for e in SandboxEnvironmentStatus}
        assert vals == {
            "provisioning",
            "provisioning_failed",
            "active",
            "suspended",
            "expired",
            "archived",
            "deleted",
        }

    def test_provisioning_job_status_values(self):
        from app.models.provisioning_job import ProvisioningJobStatus

        vals = {e.value for e in ProvisioningJobStatus}
        assert vals == {"pending", "running", "succeeded", "failed"}

    def test_sandbox_usage_event_type_values(self):
        from app.models.sandbox_usage_event import SandboxUsageEventType

        vals = {e.value for e in SandboxUsageEventType}
        assert "login" in vals
        assert "onboarding_step_completed" in vals
        assert "extension_requested" in vals
        assert len(vals) == 13


# ─────────────────────────────────────────────────────────────────────────────
# 3. Clock
# ─────────────────────────────────────────────────────────────────────────────


class TestClock:
    def test_system_clock_returns_aware_utc(self):
        from app.lib.time import SystemClock

        clock = SystemClock()
        now = clock.utcnow()
        assert now.tzinfo is not None
        assert now.tzinfo == UTC or str(now.tzinfo) in ("UTC", "utc")

    def test_frozen_clock_default_returns_fixed_time(self):
        from app.lib.time import FrozenClock

        clock = FrozenClock()
        t1 = clock.utcnow()
        t2 = clock.utcnow()
        assert t1 == t2, "FrozenClock must return same time on repeated calls"

    def test_frozen_clock_custom_time(self):
        from app.lib.time import FrozenClock

        fixed = datetime(2030, 1, 15, 9, 0, 0, tzinfo=UTC)
        clock = FrozenClock(frozen_at=fixed)
        assert clock.utcnow() == fixed

    def test_frozen_clock_advance(self):
        from app.lib.time import FrozenClock

        fixed = datetime(2030, 1, 15, 9, 0, 0, tzinfo=UTC)
        clock = FrozenClock(frozen_at=fixed)
        clock.advance(days=1)
        assert clock.utcnow().day == 16

    def test_frozen_clock_is_aware(self):
        from app.lib.time import FrozenClock

        clock = FrozenClock()
        assert clock.utcnow().tzinfo is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Protocol conformance
# ─────────────────────────────────────────────────────────────────────────────


class TestProtocols:
    def test_sandbox_feature_gate_protocol_importable(self):
        from app.interfaces.sandbox import SandboxFeatureGateProtocol

        assert SandboxFeatureGateProtocol is not None

    def test_template_seeder_protocol_importable(self):
        from app.interfaces.sandbox import TemplateSeederProtocol

        assert TemplateSeederProtocol is not None

    def test_sandbox_feature_gate_protocol_methods(self):
        from app.interfaces.sandbox import SandboxFeatureGateProtocol

        expected_methods = {
            "get_flags",
            "is_destructive_operations_disabled",
            "is_external_integrations_disabled",
            "is_platform_admin_hidden",
        }
        defined = set(name for name in dir(SandboxFeatureGateProtocol) if not name.startswith("_"))
        assert expected_methods <= defined, (
            f"Missing protocol methods: {expected_methods - defined}"
        )

    def test_template_seeder_protocol_has_seed_method(self):
        from app.interfaces.sandbox import TemplateSeederProtocol

        assert "seed" in dir(TemplateSeederProtocol)

    def test_concrete_class_satisfies_gate_protocol(self):
        """A minimal concrete class should satisfy the protocol check."""
        from app.interfaces.sandbox import SandboxFeatureGateProtocol

        class _ConcreteGate:
            def get_flags(self, tenant_id):
                return {}

            def is_destructive_operations_disabled(self, tenant_id):
                return False

            def is_external_integrations_disabled(self, tenant_id):
                return False

            def is_platform_admin_hidden(self, tenant_id):
                return False

        assert isinstance(_ConcreteGate(), SandboxFeatureGateProtocol)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Repository: public method signatures
# ─────────────────────────────────────────────────────────────────────────────


class TestRepositorySignatures:
    def _assert_methods(self, cls, methods):
        for method_name in methods:
            assert hasattr(cls, method_name), f"{cls.__name__} missing method: {method_name}"

    def test_demo_request_repository_methods(self):
        from app.services.sandbox.demo_request_repository import DemoRequestRepository

        self._assert_methods(
            DemoRequestRepository,
            [
                "create",
                "update_status",
                "find_by_id",
                "find_by_public_token",
                "find_active_by_email",
                "list_with_filters",
            ],
        )

    def test_sandbox_environment_repository_methods(self):
        from app.services.sandbox.sandbox_environment_repository import SandboxEnvironmentRepository

        self._assert_methods(
            SandboxEnvironmentRepository,
            [
                "create",
                "find_by_id",
                "find_by_tenant",
                "update_status",
                "list_expiring",
                "list_ready_for_cleanup",
                "increment_extension",
                "update_last_activity",
            ],
        )

    def test_sandbox_usage_event_repository_methods(self):
        from app.services.sandbox.sandbox_usage_event_repository import SandboxUsageEventRepository

        self._assert_methods(
            SandboxUsageEventRepository,
            [
                "insert",
                "bulk_insert",
                "summarise_by_sandbox",
                "total_events",
            ],
        )

    def test_sandbox_extension_repository_methods(self):
        from app.services.sandbox.sandbox_extension_repository import SandboxExtensionRepository

        self._assert_methods(
            SandboxExtensionRepository,
            [
                "create",
                "count_by_sandbox",
                "list_by_sandbox",
            ],
        )

    def test_provisioning_job_repository_methods(self):
        from app.services.sandbox.provisioning_job_repository import ProvisioningJobRepository

        self._assert_methods(
            ProvisioningJobRepository,
            [
                "create",
                "find_by_id",
                "find_latest_for_request",
                "update",
            ],
        )

    def test_demo_template_repository_methods(self):
        from app.services.sandbox.demo_template_repository import DemoTemplateRepository

        self._assert_methods(
            DemoTemplateRepository,
            [
                "find_by_id",
                "list_enabled",
                "list_all",
            ],
        )

    def test_access_profile_repository_methods(self):
        from app.services.sandbox.access_profile_repository import AccessProfileRepository

        self._assert_methods(
            AccessProfileRepository,
            [
                "find_by_id",
                "find_by_code",
                "list_enabled",
            ],
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. DemoRequestRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


def _mock_row(data: dict):
    """Create a mock row where ._mapping[key] works."""
    row = MagicMock()
    row._mapping = data
    return row


def _mock_result(rows):
    result = MagicMock()
    if isinstance(rows, list):
        result.fetchall.return_value = rows
        result.fetchone.return_value = rows[0] if rows else None
    else:
        result.fetchone.return_value = rows
        result.fetchall.return_value = [rows] if rows else []
    return result


class TestDemoRequestRepository:
    def _make_repo(self, execute_return):
        db = MagicMock()
        db.execute.return_value = _mock_result(execute_return)
        from app.services.sandbox.demo_request_repository import DemoRequestRepository

        return DemoRequestRepository(db), db

    def test_create_returns_dict(self):
        expected = {
            "id": str(uuid4()),
            "status": "submitted",
            "public_status_token": "tok123",
            "work_email": "a@b.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "company_name": "Acme",
            "created_at": None,
            "updated_at": None,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.create(
            work_email="a@b.com",
            first_name="Alice",
            last_name="Smith",
            company_name="Acme",
            job_title=None,
            team_size="1-10",
            country="US",
            primary_use_case="DQ testing",
            stack={},
            heard_about_us=None,
            consent=True,
            is_personal_email=False,
            public_status_token="tok123",
        )
        assert result["work_email"] == "a@b.com"
        db.execute.assert_called_once()

    def test_find_by_id_returns_none_for_missing(self):
        repo, db = self._make_repo(None)
        result = repo.find_by_id(uuid4())
        assert result is None

    def test_find_by_id_returns_dict(self):
        expected = {"id": str(uuid4()), "status": "submitted", "work_email": "x@y.com"}
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.find_by_id(uuid4())
        assert result["status"] == "submitted"

    def test_find_by_public_token_returns_dict(self):
        expected = {"id": str(uuid4()), "status": "active", "public_status_token": "abc"}
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.find_by_public_token("abc")
        assert result["public_status_token"] == "abc"

    def test_find_active_by_email_returns_none(self):
        repo, db = self._make_repo(None)
        result = repo.find_active_by_email("no@where.com")
        assert result is None

    def test_list_with_filters_returns_tuple(self):
        rows = [
            _mock_row(
                {
                    "id": str(uuid4()),
                    "status": "submitted",
                    "work_email": "t@u.com",
                    "total_count": 1,
                    "public_status_token": "t",
                    "first_name": "A",
                    "last_name": "B",
                    "company_name": "C",
                    "is_personal_email": False,
                    "created_at": None,
                    "updated_at": None,
                }
            )
        ]
        repo, db = self._make_repo(rows)
        items, total = repo.list_with_filters()
        assert isinstance(items, list)
        assert total == 1

    def test_list_with_filters_invalid_sort_defaults(self):
        repo, db = self._make_repo([])
        items, total = repo.list_with_filters(sort_by="evil; DROP TABLE", sort_dir="sideways")
        # Should not raise; invalid values are sanitised
        assert total == 0

    def test_update_status_returns_dict(self):
        expected = {"id": str(uuid4()), "status": "approved", "updated_at": None}
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.update_status(request_id=uuid4(), status="approved")
        assert result["status"] == "approved"


# ─────────────────────────────────────────────────────────────────────────────
# 7. SandboxEnvironmentRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


class TestSandboxEnvironmentRepository:
    def _make_repo(self, execute_return):
        db = MagicMock()
        db.execute.return_value = _mock_result(execute_return)
        from app.services.sandbox.sandbox_environment_repository import SandboxEnvironmentRepository

        return SandboxEnvironmentRepository(db), db

    def test_create_returns_dict(self):
        expected = {
            "id": str(uuid4()),
            "demo_request_id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "workspace_id": str(uuid4()),
            "template_id": "general_dq",
            "access_profile_id": str(uuid4()),
            "status": "provisioning",
            "expires_at": None,
            "created_at": None,
            "updated_at": None,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.create(
            demo_request_id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            template_id="general_dq",
            access_profile_id=uuid4(),
        )
        assert result["status"] == "provisioning"

    def test_find_by_id_none(self):
        repo, db = self._make_repo(None)
        assert repo.find_by_id(uuid4()) is None

    def test_list_expiring_returns_list(self):
        repo, db = self._make_repo([])
        result = repo.list_expiring(threshold_at=datetime.now(tz=UTC))
        assert result == []

    def test_list_ready_for_cleanup_returns_list(self):
        repo, db = self._make_repo([])
        result = repo.list_ready_for_cleanup(threshold_at=datetime.now(tz=UTC))
        assert result == []

    def test_increment_extension_returns_dict(self):
        expected = {"id": str(uuid4()), "extension_count": 1, "expires_at": None}
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.increment_extension(
            sandbox_id=uuid4(),
            new_expires_at=datetime.now(tz=UTC),
        )
        assert result["extension_count"] == 1

    def test_update_last_activity_executes(self):
        repo, db = self._make_repo(None)
        repo.update_last_activity(
            sandbox_id=uuid4(),
            occurred_at=datetime.now(tz=UTC),
        )
        db.execute.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 8. SandboxUsageEventRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


class TestSandboxUsageEventRepository:
    def _make_repo(self, execute_return=None):
        db = MagicMock()
        if execute_return is None:
            db.execute.return_value = _mock_result([])
        else:
            db.execute.return_value = _mock_result(execute_return)
        from app.services.sandbox.sandbox_usage_event_repository import SandboxUsageEventRepository

        return SandboxUsageEventRepository(db), db

    def test_insert_calls_execute(self):
        repo, db = self._make_repo()
        repo.insert(sandbox_id=uuid4(), user_id=uuid4(), event_type="login")
        db.execute.assert_called_once()

    def test_bulk_insert_calls_execute_per_event(self):
        repo, db = self._make_repo()
        events = [
            {"sandbox_id": uuid4(), "user_id": None, "event_type": "login"},
            {"sandbox_id": uuid4(), "user_id": uuid4(), "event_type": "page_view"},
        ]
        repo.bulk_insert(events)
        assert db.execute.call_count == 2

    def test_summarise_returns_list(self):
        repo, db = self._make_repo([])
        result = repo.summarise_by_sandbox(sandbox_id=uuid4(), since=datetime.now(tz=UTC))
        assert result == []

    def test_total_events_returns_zero(self):
        row = _mock_row({"total": 0})
        repo, db = self._make_repo(row)
        assert repo.total_events(sandbox_id=uuid4()) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 9. SandboxExtensionRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


class TestSandboxExtensionRepository:
    def _make_repo(self, execute_return=None):
        db = MagicMock()
        db.execute.return_value = _mock_result(execute_return or [])
        from app.services.sandbox.sandbox_extension_repository import SandboxExtensionRepository

        return SandboxExtensionRepository(db), db

    def test_create_returns_dict(self):
        now = datetime.now(tz=UTC)
        expected = {
            "id": str(uuid4()),
            "sandbox_id": str(uuid4()),
            "extension_days": 3,
            "new_expires_at": now,
            "created_at": now,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.create(
            sandbox_id=uuid4(),
            extended_by=None,
            extension_days=3,
            note="Need more time",
            previous_expires_at=now,
            new_expires_at=now,
        )
        assert result["extension_days"] == 3

    def test_count_returns_zero(self):
        row = _mock_row({"n": 0})
        repo, db = self._make_repo(row)
        assert repo.count_by_sandbox(uuid4()) == 0

    def test_list_returns_empty(self):
        repo, db = self._make_repo([])
        assert repo.list_by_sandbox(uuid4()) == []


# ─────────────────────────────────────────────────────────────────────────────
# 10. ProvisioningJobRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


class TestProvisioningJobRepository:
    def _make_repo(self, execute_return=None):
        db = MagicMock()
        db.execute.return_value = _mock_result(execute_return)
        from app.services.sandbox.provisioning_job_repository import ProvisioningJobRepository

        return ProvisioningJobRepository(db), db

    def test_create_returns_dict(self):
        expected = {
            "id": str(uuid4()),
            "demo_request_id": str(uuid4()),
            "status": "pending",
            "created_at": None,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.create(demo_request_id=uuid4())
        assert result["status"] == "pending"

    def test_find_by_id_none(self):
        repo, db = self._make_repo(None)
        assert repo.find_by_id(uuid4()) is None

    def test_find_latest_for_request_none(self):
        repo, db = self._make_repo(None)
        assert repo.find_latest_for_request(uuid4()) is None

    def test_update_returns_dict(self):
        expected = {
            "id": str(uuid4()),
            "status": "running",
            "attempt_count": 1,
            "updated_at": None,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.update(job_id=uuid4(), status="running", increment_attempt=1)
        assert result["status"] == "running"


# ─────────────────────────────────────────────────────────────────────────────
# 11. DemoTemplateRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


class TestDemoTemplateRepository:
    def _make_repo(self, execute_return=None):
        db = MagicMock()
        db.execute.return_value = _mock_result(execute_return or [])
        from app.services.sandbox.demo_template_repository import DemoTemplateRepository

        return DemoTemplateRepository(db), db

    def test_find_by_id_none(self):
        repo, db = self._make_repo(None)
        assert repo.find_by_id("nonexistent") is None

    def test_find_by_id_returns_dict(self):
        expected = {
            "id": "general_dq",
            "display_name": "General DQ",
            "description": "...",
            "seeder_module": "app.services.demo.templates.general_dq",
            "default_duration_days": 7,
            "is_enabled": True,
            "created_at": None,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.find_by_id("general_dq")
        assert result["id"] == "general_dq"

    def test_list_enabled_returns_list(self):
        repo, db = self._make_repo([])
        result = repo.list_enabled()
        assert result == []

    def test_list_all_returns_list(self):
        repo, db = self._make_repo([])
        result = repo.list_all()
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 12. AccessProfileRepository — mocked DB
# ─────────────────────────────────────────────────────────────────────────────


class TestAccessProfileRepository:
    def _make_repo(self, execute_return=None):
        db = MagicMock()
        db.execute.return_value = _mock_result(execute_return)
        from app.services.sandbox.access_profile_repository import AccessProfileRepository

        return AccessProfileRepository(db), db

    def test_find_by_id_none(self):
        repo, db = self._make_repo(None)
        assert repo.find_by_id(uuid4()) is None

    def test_find_by_code_none(self):
        repo, db = self._make_repo(None)
        assert repo.find_by_code("nonexistent") is None

    def test_find_by_code_returns_dict(self):
        expected = {
            "id": str(uuid4()),
            "code": "mvp_default",
            "display_name": "MVP",
            "flags": {},
            "default_role": "sandbox_admin",
            "is_enabled": True,
            "created_at": None,
        }
        repo, db = self._make_repo(_mock_row(expected))
        result = repo.find_by_code("mvp_default")
        assert result["code"] == "mvp_default"

    def test_list_enabled_returns_list(self):
        db = MagicMock()
        db.execute.return_value = _mock_result([])
        from app.services.sandbox.access_profile_repository import AccessProfileRepository

        repo = AccessProfileRepository(db)
        result = repo.list_enabled()
        assert result == []
