"""
F073 P01 — Unit tests: ExecutionEngine

Tests SQL safety validation, engine caching, dry-run, and execute_rule error handling.

engine.py imports schemas that don't exist yet (RuleExecution, GeneratedRule, etc.),
so we pre-populate sys.modules with stubs before the import.

P01-01 .. P01-15  (15 tests)
"""

from __future__ import annotations

import sys
import types
from datetime import datetime
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub schema types that engine.py expects
# ---------------------------------------------------------------------------
class _ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class _StubBase:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _ExecutionResult(_StubBase):
    pass


class _Explanation(_StubBase):
    pass


class _RuleExecution(_StubBase):
    pass


class _GeneratedRule(_StubBase):
    pass


class _DataSource(_StubBase):
    pass


# Patch schemas into sys.modules BEFORE importing engine
_saved_modules = {}
_stub_keys = ["app.schemas.rule", "app.services.llm", "app.services.llm.orchestrator"]
for _k in _stub_keys:
    if _k in sys.modules:
        _saved_modules[_k] = sys.modules[_k]

_fake_rule = types.ModuleType("app.schemas.rule")
_fake_rule.RuleExecution = _RuleExecution
_fake_rule.ExecutionResult = _ExecutionResult
_fake_rule.ExecutionStatus = _ExecutionStatus
_fake_rule.Explanation = _Explanation
_fake_rule.GeneratedRule = _GeneratedRule
_fake_rule.DataSource = _DataSource
sys.modules["app.schemas.rule"] = _fake_rule

# Also stub the llm_orchestrator import
_fake_orchestrator_mod = types.ModuleType("app.services.llm.orchestrator")
_fake_orchestrator_mod.llm_orchestrator = MagicMock()
sys.modules.setdefault("app.services.llm", types.ModuleType("app.services.llm"))
sys.modules["app.services.llm.orchestrator"] = _fake_orchestrator_mod

# NOW import engine
from app.services.execution.engine import ExecutionEngine  # noqa: E402

# Restore sys.modules so other test files can import real schemas
for _k in _stub_keys:
    if _k in _saved_modules:
        sys.modules[_k] = _saved_modules[_k]
    else:
        sys.modules.pop(_k, None)

ENGINE_MODULE = "app.services.execution.engine"


def _engine():
    """Create a fresh ExecutionEngine instance."""
    return ExecutionEngine()


def _mock_rule(**overrides):
    r = MagicMock()
    r.rule_id = overrides.get("rule_id", "rule-1")
    r.sql = overrides.get("sql", "SELECT * FROM t WHERE x IS NULL")
    r.pyspark = overrides.get("pyspark", "")
    r.original_prompt = "test prompt"
    return r


def _mock_datasource(**overrides):
    ds = MagicMock()
    ds.type = overrides.get("type", "postgresql")
    ds.connection_id = overrides.get("connection_id", "conn-1")
    ds.connection_string = overrides.get("connection_string", "postgresql://localhost/test")
    ds.schema_name = overrides.get("schema_name", "public")
    ds.table = overrides.get("table", "users")
    return ds


# ===================================================================
# SQL SAFETY VALIDATION
# ===================================================================
class TestValidateSqlSafety:
    def test_select_allowed(self):
        """P01-01"""
        e = _engine()
        e._validate_sql_safety("SELECT * FROM users WHERE age > 18")

    def test_with_cte_allowed(self):
        """P01-02"""
        e = _engine()
        e._validate_sql_safety("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_insert_rejected(self):
        """P01-03"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("INSERT INTO users VALUES (1)")

    def test_drop_rejected(self):
        """P01-04"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("DROP TABLE users")

    def test_delete_rejected(self):
        """P01-05"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("DELETE FROM users WHERE 1=1")

    def test_update_rejected(self):
        """P01-06"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("UPDATE users SET name='x'")

    def test_mixed_case_rejected(self):
        """P01-07"""
        e = _engine()
        with pytest.raises(ValueError):
            e._validate_sql_safety("DrOp TaBlE users")

    def test_alter_rejected(self):
        """P01-08"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("ALTER TABLE users ADD col int")

    def test_truncate_rejected(self):
        """P01-09"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("TRUNCATE TABLE users")

    def test_grant_rejected(self):
        """P01-10"""
        e = _engine()
        with pytest.raises(ValueError, match="Only SELECT"):
            e._validate_sql_safety("GRANT ALL ON users TO public")


# ===================================================================
# GET ENGINE (caching)
# ===================================================================
class TestGetEngine:
    def test_caches_by_connection_id(self):
        """P01-11"""
        e = _engine()
        ds = _mock_datasource()
        with patch(f"{ENGINE_MODULE}.create_engine") as mock_ce:
            mock_ce.return_value = MagicMock()
            e1 = e._get_engine(ds)
            e2 = e._get_engine(ds)
            assert e1 is e2
            mock_ce.assert_called_once()

    def test_different_ids_different_engines(self):
        """P01-12"""
        e = _engine()
        ds1 = _mock_datasource(connection_id="a")
        ds2 = _mock_datasource(connection_id="b")
        with patch(f"{ENGINE_MODULE}.create_engine") as mock_ce:
            mock_ce.return_value = MagicMock()
            e._get_engine(ds1)
            e._get_engine(ds2)
            assert mock_ce.call_count == 2


# ===================================================================
# DRY RUN
# ===================================================================
class TestCreateDryRunResult:
    def test_returns_100_pass_rate(self):
        """P01-13"""
        e = _engine()
        rule = _mock_rule()
        ds = _mock_datasource()
        result = e._create_dry_run_result("exec-1", rule, ds, datetime.utcnow())
        assert result.results.pass_rate == 1.0
        assert result.results.violation_count == 0


# ===================================================================
# EXECUTE RULE
# ===================================================================
class TestExecuteRule:
    @pytest.mark.asyncio
    async def test_dry_run_skips_execution(self):
        """P01-14: dry_run=True → _execute_sql not called"""
        e = _engine()
        rule = _mock_rule()
        ds = _mock_datasource()
        result = await e.execute_rule(rule, ds, dry_run=True)
        assert result.results.pass_rate == 1.0

    @pytest.mark.asyncio
    async def test_exception_returns_failed(self):
        """P01-15: Exception in SQL → FAILED status"""
        e = _engine()
        rule = _mock_rule(sql="SELECT * FROM t")
        ds = _mock_datasource()

        with patch.object(e, "_execute_sql", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = Exception("connection refused")
            result = await e.execute_rule(rule, ds, dry_run=False)

        assert result.status == _ExecutionStatus.FAILED
        assert "connection refused" in result.error
