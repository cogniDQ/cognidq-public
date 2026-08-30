"""
F-CONN-CORE — Lifecycle state machine tests (spec §11 + §12).

Verifies the connection and dataset state machines defined in
``backend/app/services/connections/lifecycle.py`` and
``backend/app/services/datasets/lifecycle.py`` plus the migration alignment
on the underlying CHECK constraints.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.services.connections.lifecycle import (
    ConnectionState,
    IllegalConnectionTransitionError,
)
from app.services.connections.lifecycle import (
    allowed_next as conn_allowed_next,
)
from app.services.connections.lifecycle import (
    assert_transition as conn_assert_transition,
)
from app.services.connections.lifecycle import (
    can_transition as conn_can_transition,
)
from app.services.datasets.lifecycle import (
    DatasetState,
    IllegalDatasetTransitionError,
)
from app.services.datasets.lifecycle import (
    allowed_next as ds_allowed_next,
)
from app.services.datasets.lifecycle import (
    assert_transition as ds_assert_transition,
)
from app.services.datasets.lifecycle import (
    can_transition as ds_can_transition,
)

# ─── Connection lifecycle ───────────────────────────────────────────────────


class TestConnectionLifecycle:
    def test_spec_11_states_present(self):
        # spec §11
        assert {s.value for s in ConnectionState} >= {
            "draft",
            "created",
            "test_failed",
            "test_successful",
            "discovery_available",
            "active",
            "disabled",
            "archived",
        }

    def test_happy_path_draft_to_active(self):
        cur = "draft"
        for nxt in (
            "created",
            "test_successful",
            "discovery_available",
            "active",
        ):
            cur = conn_assert_transition(cur, nxt).value

    def test_test_failed_can_retry(self):
        conn_assert_transition("created", "test_failed")
        conn_assert_transition("test_failed", "created")
        conn_assert_transition("test_failed", "test_successful")

    def test_active_can_disable_and_reenable(self):
        conn_assert_transition("active", "disabled")
        conn_assert_transition("disabled", "active")

    def test_any_state_can_archive(self):
        for s in (
            "draft",
            "created",
            "test_failed",
            "test_successful",
            "discovery_available",
            "active",
            "disabled",
        ):
            assert conn_can_transition(s, "archived")

    def test_archived_is_terminal(self):
        assert not conn_can_transition("archived", "active")
        assert not conn_can_transition("archived", "draft")
        with pytest.raises(IllegalConnectionTransitionError):
            conn_assert_transition("archived", "active")

    def test_idempotent_self_transition(self):
        assert conn_can_transition("active", "active")
        assert conn_can_transition("archived", "archived")

    def test_illegal_jump_rejected(self):
        # cannot skip from draft directly to active
        with pytest.raises(IllegalConnectionTransitionError):
            conn_assert_transition("draft", "active")
        # cannot go backwards from active to created
        with pytest.raises(IllegalConnectionTransitionError):
            conn_assert_transition("active", "created")

    def test_unknown_state_rejected(self):
        with pytest.raises(ValueError):
            conn_assert_transition("nonsense", "active")

    def test_allowed_next_includes_archive(self):
        assert ConnectionState.ARCHIVED in conn_allowed_next("active")
        assert conn_allowed_next("archived") == frozenset()


# ─── Dataset lifecycle ──────────────────────────────────────────────────────


class TestDatasetLifecycle:
    def test_spec_12_states_present(self):
        assert {s.value for s in DatasetState} >= {
            "discovered",
            "registered",
            "active",
            "checked",
            "inaccessible",
            "archived",
        }

    def test_happy_path_discovered_to_checked(self):
        cur = "discovered"
        for nxt in ("registered", "active", "checked"):
            cur = ds_assert_transition(cur, nxt).value

    def test_checked_returns_to_active(self):
        ds_assert_transition("checked", "active")

    def test_inaccessible_round_trip(self):
        ds_assert_transition("active", "inaccessible")
        ds_assert_transition("inaccessible", "active")

    def test_legacy_draft_can_promote(self):
        # F005 datasets currently start as 'draft'; the new state machine
        # must let them migrate forward without a manual data fix.
        ds_assert_transition("draft", "registered")
        ds_assert_transition("draft", "active")
        ds_assert_transition("inactive", "active")

    def test_any_state_can_archive(self):
        for s in (
            "discovered",
            "registered",
            "active",
            "checked",
            "inaccessible",
            "draft",
            "inactive",
        ):
            assert ds_can_transition(s, "archived")

    def test_archived_is_terminal(self):
        with pytest.raises(IllegalDatasetTransitionError):
            ds_assert_transition("archived", "active")

    def test_illegal_jump_rejected(self):
        # cannot skip discovered → active without registering first
        with pytest.raises(IllegalDatasetTransitionError):
            ds_assert_transition("discovered", "active")
        # cannot regress active → registered
        with pytest.raises(IllegalDatasetTransitionError):
            ds_assert_transition("active", "registered")

    def test_idempotent_self_transition(self):
        assert ds_can_transition("active", "active")

    def test_allowed_next_includes_archive(self):
        assert DatasetState.ARCHIVED in ds_allowed_next("active")
        assert ds_allowed_next("archived") == frozenset()


# ─── Migration 042 alignment ─────────────────────────────────────────────────


def _read_migration() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrations"
        / "042_connection_dataset_lifecycle.sql"
    )
    return path.read_text(encoding="utf-8")


def _allowed_values(sql: str, table: str) -> set:
    pattern = re.compile(
        rf"ALTER TABLE\s+control\.{table}\s+ADD CONSTRAINT\s+ck_{table}_status\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(sql)
    assert m, f"Could not locate CHECK clause for {table} in migration"
    raw = m.group(1)
    # Drop SQL line comments so values immediately after a `--` line are preserved.
    raw = re.sub(r"--[^\n]*", "", raw)
    return {v.strip().strip("'") for v in raw.split(",") if v.strip().startswith("'")}


class TestMigrationAlignment:
    def test_data_sources_check_includes_all_connection_states(self):
        sql = _read_migration()
        allowed = _allowed_values(sql, "data_sources")
        for state in ConnectionState:
            assert state.value in allowed, (
                f"Migration 042 CHECK on data_sources is missing {state.value!r}"
            )

    def test_data_sources_preserves_legacy_values(self):
        sql = _read_migration()
        allowed = _allowed_values(sql, "data_sources")
        # spec §11 already includes 'active' + 'archived' (the legacy values)
        assert {"active", "archived"} <= allowed

    def test_datasets_check_includes_all_dataset_states(self):
        sql = _read_migration()
        allowed = _allowed_values(sql, "datasets")
        for state in DatasetState:
            assert state.value in allowed, (
                f"Migration 042 CHECK on datasets is missing {state.value!r}"
            )

    def test_datasets_preserves_legacy_values(self):
        sql = _read_migration()
        allowed = _allowed_values(sql, "datasets")
        # F005 currently uses these values
        assert {"draft", "active", "inactive", "archived"} <= allowed
