"""
F002 — Dataset and Member Registry interfaces and stubs
=========================================================

Provides two read-only registry interfaces used by the detail endpoint:

* ``DatasetRegistryInterface`` — counts datasets associated with a workspace.
* ``MemberRegistryInterface``  — counts members (role-grant holders) for a
  workspace.

Both interfaces return a plain ``int`` and raise on error or timeout.  The
caller (``WorkspaceService.get_workspace_detail``) catches all exceptions
and falls back to ``None`` with a ``warnings`` entry, per TDD §11.3.

Stub implementations
--------------------
``DatasetRegistryStub`` and ``MemberRegistryStub`` are used in all F002
packets and tests.  They accept two optional constructor arguments:

* ``return_value`` — the integer to return on success (default ``0``).
* ``raise_error``  — when ``True``, raises ``RuntimeError`` on every call,
  simulating a registry outage or timeout (default ``False``).

The real implementations are delivered in other feature packets that own
the dataset and RBAC registries.  All F002 code depends only on the
abstract interfaces.
"""

from __future__ import annotations

import abc
import uuid

# ---------------------------------------------------------------------------
# Dataset Registry
# ---------------------------------------------------------------------------


class DatasetRegistryInterface(abc.ABC):
    """
    Abstract contract for counting datasets linked to a workspace.

    Raises
    ------
    Exception
        On registry error or timeout; callers must catch all exceptions.
    """

    @abc.abstractmethod
    def count_for_workspace(
        self,
        workspace_id: uuid.UUID,
        timeout_ms: int = 3000,
    ) -> int:
        """
        Return the dataset count for *workspace_id*.

        Parameters
        ----------
        workspace_id:
            Target workspace.
        timeout_ms:
            Maximum allowed query time in milliseconds.

        Raises
        ------
        Exception
            On error or timeout; callers must catch and fall back to ``None``.
        """


class DatasetRegistryStub(DatasetRegistryInterface):
    """
    Development/test stub for ``DatasetRegistryInterface``.

    Parameters
    ----------
    return_value:
        Value returned by calls when ``raise_error=False``.
    raise_error:
        When ``True``, every call raises ``RuntimeError`` to simulate a
        registry outage or query timeout.
    """

    def __init__(self, return_value: int = 0, raise_error: bool = False) -> None:
        self._return_value = return_value
        self._raise_error = raise_error

    def count_for_workspace(
        self,
        workspace_id: uuid.UUID,
        timeout_ms: int = 3000,
    ) -> int:
        if self._raise_error:
            raise RuntimeError(f"DatasetRegistry unavailable (stub, workspace_id={workspace_id})")
        return self._return_value


# ---------------------------------------------------------------------------
# Member Registry
# ---------------------------------------------------------------------------


class MemberRegistryInterface(abc.ABC):
    """
    Abstract contract for counting members (role holders) of a workspace.

    This is distinct from ``RBACServiceInterface`` (which grants roles).
    This interface only reads membership counts.

    Raises
    ------
    Exception
        On registry error or timeout; callers must catch all exceptions.
    """

    @abc.abstractmethod
    def count_members_for_workspace(
        self,
        workspace_id: uuid.UUID,
        timeout_ms: int = 3000,
    ) -> int:
        """
        Return the member count for *workspace_id*.

        Parameters
        ----------
        workspace_id:
            Target workspace.
        timeout_ms:
            Maximum allowed query time in milliseconds.

        Raises
        ------
        Exception
            On error or timeout; callers must catch and fall back to ``None``.
        """


class MemberRegistryStub(MemberRegistryInterface):
    """
    Development/test stub for ``MemberRegistryInterface``.

    Parameters
    ----------
    return_value:
        Value returned by calls when ``raise_error=False``.
    raise_error:
        When ``True``, every call raises ``RuntimeError`` to simulate a
        registry outage or query timeout.
    """

    def __init__(self, return_value: int = 0, raise_error: bool = False) -> None:
        self._return_value = return_value
        self._raise_error = raise_error

    def count_members_for_workspace(
        self,
        workspace_id: uuid.UUID,
        timeout_ms: int = 3000,
    ) -> int:
        if self._raise_error:
            raise RuntimeError(f"MemberRegistry unavailable (stub, workspace_id={workspace_id})")
        return self._return_value


# ---------------------------------------------------------------------------
# Real implementations (Sprint 4.7)
# ---------------------------------------------------------------------------


class WorkspaceDatasetRegistry(DatasetRegistryInterface):
    """Real `DatasetRegistryInterface` backed by ``control.datasets``.

    Counts non-archived datasets attached to the given workspace.
    Uses a session-local ``statement_timeout`` so a slow query cannot stall
    the workspace detail endpoint.
    """

    def __init__(self, db) -> None:  # type: ignore[no-untyped-def]
        self._db = db

    def count_for_workspace(
        self,
        workspace_id: uuid.UUID,
        timeout_ms: int = 3000,
    ) -> int:
        from sqlalchemy import text

        # Inspect once so a missing schema gracefully degrades (instead of
        # raising a SQL error that would surface as a generic warning).
        exists = self._db.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='control' AND table_name='datasets' LIMIT 1
                """
            )
        ).fetchone()
        if exists is None:
            return 0

        # Detect the optional ``status`` column so older deployments still
        # return a count.
        has_status = (
            self._db.execute(
                text(
                    """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='control' AND table_name='datasets'
                  AND column_name='status' LIMIT 1
                """
                )
            ).fetchone()
            is not None
        )

        timeout_sec = max(1, int(timeout_ms / 1000))
        self._db.execute(text(f"SET LOCAL statement_timeout = {timeout_sec * 1000}"))

        if has_status:
            sql = (
                "SELECT COUNT(*) FROM control.datasets "
                "WHERE workspace_id = CAST(:wid AS UUID) "
                "  AND COALESCE(status, 'active') <> 'archived'"
            )
        else:
            sql = "SELECT COUNT(*) FROM control.datasets WHERE workspace_id = CAST(:wid AS UUID)"
        row = self._db.execute(text(sql), {"wid": str(workspace_id)}).fetchone()
        return int(row[0]) if row and row[0] is not None else 0


class WorkspaceMemberRegistry(MemberRegistryInterface):
    """Real `MemberRegistryInterface` backed by
    ``control.workspace_role_assignments``.

    Counts DISTINCT users with at least one role grant in the workspace.
    """

    def __init__(self, db) -> None:  # type: ignore[no-untyped-def]
        self._db = db

    def count_members_for_workspace(
        self,
        workspace_id: uuid.UUID,
        timeout_ms: int = 3000,
    ) -> int:
        from sqlalchemy import text

        exists = self._db.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='control' AND table_name='workspace_role_assignments'
                LIMIT 1
                """
            )
        ).fetchone()
        if exists is None:
            return 0

        timeout_sec = max(1, int(timeout_ms / 1000))
        self._db.execute(text(f"SET LOCAL statement_timeout = {timeout_sec * 1000}"))

        row = self._db.execute(
            text(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM control.workspace_role_assignments
                WHERE workspace_id = CAST(:wid AS UUID)
                """
            ),
            {"wid": str(workspace_id)},
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
