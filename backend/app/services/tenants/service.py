"""
F001 — TenantService
======================

Implements the full 7-step CREATE flow from TDD §4.2:

    1. Receive CreateTenantCommand (already normalised + validated by the endpoint)
    2. Open transaction
    3a. Check uniqueness of tenant_name (pre-check SELECT)
    3b. Check uniqueness of tenant_slug (pre-check SELECT)
    3c. Generate UUID v4 for tenant_id and audit log_id
    3d. created_at / updated_at are set via DB DEFAULT NOW()
    3e. created_by = updated_by = actor_id
    3f. version = 0
    3g. INSERT into control.tenants (RETURNING all columns)
    3h. INSERT into control.tenant_audit_logs
    4. Commit
    5. Emit metric (fire-and-forget — never fails the request)
    6. Return TenantDTO

Also implements the UPDATE flow from TDD §4.3 (Packet 6):

    1. Receive UpdateTenantCommand (validated fields by the endpoint)
    2. SELECT ... FOR UPDATE NOWAIT — acquire exclusive row lock
    3. Business-rule checks (not found, archived, status_reason guard)
    4. Compute change set; if empty → 422 no_mutable_fields
    5. Uniqueness pre-check for new tenant_name
    6. UPDATE tenant + INSERT audit log (changed fields only)
    7. Commit; return TenantDTO

Transaction safety
------------------
* autocommit=False is the SQLAlchemy session default; the session is already
  inside an implicit transaction.
* Both INSERTs/UPDATE share the same session; commit() makes them durable atomically.
* Any exception triggers rollback() before re-raising.
* A DB-level UniqueViolation (race-condition window) is caught and translated
  to the same 422 error codes as the pre-check path.
* FOR UPDATE NOWAIT: if another transaction holds the row lock, PostgreSQL
  raises LockNotAvailable (pgcode 55P03) immediately → HTTP 409 conflict.
"""

from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.tenants.commands import (
    ChangeStatusCommand,
    ChangeStatusDTO,
    CreateTenantCommand,
    TenantDetailDTO,
    TenantDTO,
    UpdateTenantCommand,
)
from app.services.tenants.metrics import (
    emit_tenant_create_failure,
    emit_tenant_create_success,
    emit_tenant_status_change,
)
from app.services.tenants.repository import (
    AuditLogRepository,
    OutboxRepository,
    TenantRepository,
    _translate_integrity_error,
)
from app.services.workspaces.repository import WorkspaceRepository as _WorkspaceRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status transition matrix (TDD §2.6)
# Key: (current_status, target_status)  →  True  = allowed
# All 16 cells are represented; unlisted (current == target) transitions are
# handled separately as no-op checks before this lookup.
# ---------------------------------------------------------------------------
_ALLOWED_TRANSITIONS: dict[tuple, bool] = {
    # from draft
    ("draft", "active"): True,
    ("draft", "suspended"): False,
    ("draft", "archived"): True,
    # from active
    ("active", "draft"): False,
    ("active", "suspended"): True,
    ("active", "archived"): True,
    # from suspended
    ("suspended", "draft"): False,
    ("suspended", "active"): True,
    ("suspended", "archived"): True,
    # from archived — all forbidden
    ("archived", "draft"): False,
    ("archived", "active"): False,
    ("archived", "suspended"): False,
    ("archived", "archived"): False,  # self-transition also forbidden (caught as no-op)
}


class TenantService:
    @staticmethod
    def create_tenant(db: Session, command: CreateTenantCommand) -> TenantDTO:
        """Execute the full create-tenant flow; return the new TenantDTO.

        Raises:
            TenantAPIError(422): on duplicate name, duplicate slug, or other
                business rule violations.
            TenantAPIError(500): on unexpected database errors.
        """
        # ------------------------------------------------------------------
        # Step 3a-b — uniqueness pre-checks (inside the implicit transaction)
        # ------------------------------------------------------------------
        if TenantRepository.check_name_exists(db, command.tenant_name):
            emit_tenant_create_failure("duplicate_name")
            raise TenantAPIError(422, "duplicate_name", "A tenant with this name already exists.")

        if TenantRepository.check_slug_exists(db, command.tenant_slug):
            emit_tenant_create_failure("duplicate_slug")
            raise TenantAPIError(422, "duplicate_slug", "A tenant with this slug already exists.")

        # ------------------------------------------------------------------
        # Step 3c — generate IDs
        # ------------------------------------------------------------------
        tenant_id = uuid.uuid4()
        log_id = uuid.uuid4()

        # ------------------------------------------------------------------
        # Steps 3d-3h — INSERT tenant + INSERT audit log, then commit
        # ------------------------------------------------------------------
        tenant_params = {
            "tenant_id": str(tenant_id),
            "tenant_name": command.tenant_name,
            "tenant_slug": command.tenant_slug,
            "status": command.initial_status,
            "status_reason": command.status_reason,
            "region": command.region,
            "plan": command.plan,
            "service_start_date": command.service_start_date,
            "tenant_notes": command.tenant_notes,
            # created_by = updated_by = actor (step 3e); version = 0 (step 3f)
            "created_by": str(command.actor_id),
            "updated_by": str(command.actor_id),
        }

        # new_data payload per TDD §2.4 — tenant_created event schema
        new_data_payload = {
            "tenant_id": str(tenant_id),
            "tenant_name": command.tenant_name,
            "tenant_slug": command.tenant_slug,
            "status": command.initial_status,
            "region": command.region,
            "plan": command.plan,
            "created_by": str(command.actor_id),
        }

        try:
            row = TenantRepository.insert(db, tenant_params)

            AuditLogRepository.insert(
                db,
                log_id=str(log_id),
                tenant_id=str(tenant_id),
                actor_id=str(command.actor_id),
                actor_role=command.actor_role,
                new_data=new_data_payload,
            )

            db.commit()  # Step 4 — atomic commit for both rows

        except TenantAPIError:
            db.rollback()
            raise

        except IntegrityError as exc:
            db.rollback()
            # Map the constraint name to the correct TDD §8.1 failure_reason label.
            # Valid values: duplicate_name, duplicate_slug, internal_error.
            # "db_constraint" is NOT a valid label per TDD §8.1.
            _orig = getattr(exc, "orig", None)
            _pgcode = getattr(_orig, "pgcode", None) if _orig is not None else None
            _constraint: str = getattr(getattr(_orig, "diag", None), "constraint_name", "") or ""
            if _pgcode == "23505":
                if "name_lower" in _constraint or "name" in _constraint:
                    emit_tenant_create_failure("duplicate_name")
                elif "slug" in _constraint:
                    emit_tenant_create_failure("duplicate_slug")
                else:
                    emit_tenant_create_failure("internal_error")
            else:
                emit_tenant_create_failure("internal_error")
            _translate_integrity_error(exc)  # always raises TenantAPIError

        except Exception:
            db.rollback()
            logger.exception("Unexpected error during tenant creation")
            emit_tenant_create_failure("internal_error")
            raise TenantAPIError(500, "internal_error", "An unexpected error occurred.")

        # ------------------------------------------------------------------
        # Step 5 — fire-and-forget metric (must never change the response)
        # ------------------------------------------------------------------
        try:
            emit_tenant_create_success(
                region=command.region,
                plan=command.plan,
                initial_status=command.initial_status,
            )
        except Exception:
            logger.exception("Metric emission failed (non-fatal); request unaffected")

        # ------------------------------------------------------------------
        # Step 6 — build and return DTO
        # ------------------------------------------------------------------
        return TenantDTO(
            tenant_id=str(row["tenant_id"]),
            tenant_name=row["tenant_name"],
            tenant_slug=row["tenant_slug"],
            status=str(row["status"]),
            status_reason=row["status_reason"],
            region=str(row["region"]),
            plan=str(row["plan"]),
            service_start_date=row["service_start_date"],
            tenant_notes=row["tenant_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
        )

    @staticmethod
    def get_tenant_detail(
        db: Session,
        tenant_id_str: str,
        workspace_client: Any,
        user_client: Any,
    ) -> TenantDetailDTO:
        """Return full tenant detail with concurrent registry counts.

        Issues both registry calls concurrently.  If either call fails
        (timeout, error, or open circuit), the affected count is returned
        as 0 and the ``_available`` flag is set to ``False``.  The HTTP
        response is always 200 OK when the tenant exists.

        Args:
            db:               Active SQLAlchemy session.
            tenant_id_str:    UUID string of the tenant (already validated).
            workspace_client: Registry client for workspace counts.
            user_client:      Registry client for user counts.

        Returns:
            TenantDetailDTO with all 18 fields.

        Raises:
            TenantAPIError(404, "not_found"): No tenant with that ID.
        """
        row = TenantRepository.find_by_id(db, tenant_id_str)
        if row is None:
            raise TenantAPIError(404, "not_found", "Tenant not found.")

        # Issue both registry calls concurrently to minimise latency.
        with ThreadPoolExecutor(max_workers=2) as executor:
            ws_future = executor.submit(
                _safe_registry_call, workspace_client, tenant_id_str, "workspace"
            )
            user_future = executor.submit(_safe_registry_call, user_client, tenant_id_str, "user")
            ws_count, ws_available = ws_future.result()
            user_count, user_available = user_future.result()

        return TenantDetailDTO(
            tenant_id=str(row["tenant_id"]),
            tenant_name=row["tenant_name"],
            tenant_slug=row["tenant_slug"],
            status=str(row["status"]),
            status_reason=row["status_reason"],
            region=str(row["region"]),
            plan=str(row["plan"]),
            service_start_date=row["service_start_date"],
            tenant_notes=row["tenant_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
            workspace_count=ws_count,
            workspace_count_available=ws_available,
            user_count=user_count,
            user_count_available=user_available,
            audit_summary_link=f"/api/v1/tenants/{row['tenant_id']}/audit-logs",
        )

    @staticmethod
    def update_tenant(db: Session, command: UpdateTenantCommand) -> TenantDTO:
        """Execute the full update-tenant flow from TDD §4.3; return the updated DTO.

        Flow:
            1. SELECT … FOR UPDATE NOWAIT — acquire row lock
            2. Not-found / archived / status_reason guard checks
            3. Build change set; if empty → 422 no_mutable_fields
            4. Uniqueness pre-check for new tenant_name
            5. UPDATE tenant + INSERT audit log
            6. Commit
            7. Return TenantDTO

        Raises:
            TenantAPIError(400 / 404 / 409 / 422): on business-rule violations
                or lock contention.
            TenantAPIError(500): on unexpected database errors.
        """
        # ------------------------------------------------------------------
        # Step 1 — SELECT … FOR UPDATE NOWAIT
        # ------------------------------------------------------------------
        try:
            row = TenantRepository.find_by_id_for_update(db, command.tenant_id)
        except OperationalError as exc:
            db.rollback()
            orig = getattr(exc, "orig", None)
            pgcode = getattr(orig, "pgcode", "") if orig is not None else ""
            if pgcode in ("55P03", "40001"):
                raise TenantAPIError(
                    409,
                    "conflict",
                    "The tenant is currently being modified by another request. Please try again.",
                ) from exc
            logger.exception("Unexpected OperationalError acquiring row lock")
            raise TenantAPIError(
                500, "internal_error", "An unexpected database error occurred."
            ) from exc
        except Exception:
            db.rollback()
            logger.exception("Unexpected error acquiring row lock")
            raise TenantAPIError(500, "internal_error", "An unexpected error occurred.")

        # ------------------------------------------------------------------
        # Step 2a — Not found
        # ------------------------------------------------------------------
        if row is None:
            db.rollback()
            raise TenantAPIError(404, "not_found", "Tenant not found.")

        # ------------------------------------------------------------------
        # Step 2b — Archived block
        # ------------------------------------------------------------------
        current_status = str(row["status"])
        if current_status == "archived":
            db.rollback()
            raise TenantAPIError(
                422,
                "archived_tenant",
                "Archived tenants cannot be modified.",
            )

        # ------------------------------------------------------------------
        # Step 2c — status_reason PATCH guard (TDD §6.6)
        # ------------------------------------------------------------------
        if "status_reason" in command.fields:
            new_sr = command.fields["status_reason"]  # None means "clear"
            if new_sr is None and current_status in ("suspended", "archived"):
                db.rollback()
                raise TenantAPIError(
                    422,
                    "status_reason_required_for_current_status",
                    "status_reason cannot be cleared while the tenant is in "
                    f"'{current_status}' status.",
                )
            if new_sr is not None and current_status in ("suspended", "archived"):
                if len(new_sr) < 10:
                    db.rollback()
                    raise TenantAPIError(
                        422,
                        "validation_error",
                        "status_reason must be at least 10 characters for a "
                        f"'{current_status}' tenant.",
                        [{"field": "status_reason", "reason": "min_length"}],
                    )

        # ------------------------------------------------------------------
        # Step 3 — Build change set; reject empty diff
        # ------------------------------------------------------------------
        changes, previous_data, new_data_dict = _build_change_set(command.fields, row)

        if not changes:
            db.rollback()
            raise TenantAPIError(
                422,
                "no_mutable_fields",
                "None of the supplied fields differ from their current values.",
            )

        # ------------------------------------------------------------------
        # Step 4 — Uniqueness pre-check for new tenant_name
        # ------------------------------------------------------------------
        if "tenant_name" in changes:
            if TenantRepository.check_name_exists_excluding(
                db, changes["tenant_name"], command.tenant_id
            ):
                db.rollback()
                raise TenantAPIError(
                    422,
                    "duplicate_name",
                    "A tenant with this name already exists.",
                )

        # ------------------------------------------------------------------
        # Step 5 — UPDATE tenant + INSERT audit log (within the same lock)
        # ------------------------------------------------------------------
        log_id = uuid.uuid4()

        try:
            updated_row = TenantRepository.update(
                db, command.tenant_id, changes, str(command.actor_id)
            )
            AuditLogRepository.insert_update(
                db,
                log_id=str(log_id),
                tenant_id=command.tenant_id,
                actor_id=str(command.actor_id),
                actor_role=command.actor_role,
                previous_data=previous_data,
                new_data=new_data_dict,
            )
            db.commit()  # Step 6 — atomic commit (releases the FOR UPDATE lock)

        except TenantAPIError:
            db.rollback()
            raise

        except IntegrityError as exc:
            db.rollback()
            _translate_integrity_error(exc)  # always raises TenantAPIError

        except Exception:
            db.rollback()
            logger.exception("Unexpected error during tenant update")
            raise TenantAPIError(500, "internal_error", "An unexpected error occurred.")

        # ------------------------------------------------------------------
        # Step 7 — Build and return DTO
        # ------------------------------------------------------------------
        return TenantDTO(
            tenant_id=str(updated_row["tenant_id"]),
            tenant_name=updated_row["tenant_name"],
            tenant_slug=updated_row["tenant_slug"],
            status=str(updated_row["status"]),
            status_reason=updated_row["status_reason"],
            region=str(updated_row["region"]),
            plan=str(updated_row["plan"]),
            service_start_date=updated_row["service_start_date"],
            tenant_notes=updated_row["tenant_notes"],
            created_at=updated_row["created_at"],
            updated_at=updated_row["updated_at"],
            created_by=str(updated_row["created_by"]),
            updated_by=str(updated_row["updated_by"]),
        )

    @staticmethod
    def change_status(db: Session, command: ChangeStatusCommand) -> ChangeStatusDTO:
        """Execute the full change-status flow from TDD §4.4; return ChangeStatusDTO.

        Flow (8 steps per TDD §4.4):
            1. SELECT … FOR UPDATE NOWAIT — acquire exclusive row lock
            2. Not found → 404
            3. No-op check (current == target) → 422 no_op_transition
            4. Transition matrix check → 422 forbidden_transition
            5. status_reason validation for suspended/archived targets
            6. UPDATE tenant status + INSERT audit log + INSERT outbox (suspended only)
            7. Commit
            8. Emit metric (fire-and-forget); return ChangeStatusDTO

        Raises:
            TenantAPIError(404): Tenant not found.
            TenantAPIError(409): Concurrent lock contention.
            TenantAPIError(422): Business-rule violation (no-op, forbidden transition,
                                 missing/invalid status_reason).
            TenantAPIError(500): Unexpected database error.
        """
        # ------------------------------------------------------------------
        # Step 1 — SELECT … FOR UPDATE NOWAIT
        # ------------------------------------------------------------------
        try:
            row = TenantRepository.find_by_id_for_update(db, command.tenant_id)
        except OperationalError as exc:
            db.rollback()
            orig = getattr(exc, "orig", None)
            pgcode = getattr(orig, "pgcode", "") if orig is not None else ""
            if pgcode in ("55P03", "40001"):
                raise TenantAPIError(
                    409,
                    "conflict",
                    "The tenant is currently being modified by another request. Please try again.",
                ) from exc
            logger.exception("Unexpected OperationalError acquiring row lock")
            raise TenantAPIError(
                500, "internal_error", "An unexpected database error occurred."
            ) from exc
        except Exception:
            db.rollback()
            logger.exception("Unexpected error acquiring row lock")
            raise TenantAPIError(500, "internal_error", "An unexpected error occurred.")

        # ------------------------------------------------------------------
        # Step 2 — Not found
        # ------------------------------------------------------------------
        if row is None:
            db.rollback()
            raise TenantAPIError(404, "not_found", "Tenant not found.")

        current_status = str(row["status"])
        target_status = command.target_status

        # ------------------------------------------------------------------
        # Step 3 — No-op detection (rollback; no audit log written)
        # ------------------------------------------------------------------
        if current_status == target_status:
            db.rollback()
            raise TenantAPIError(
                422,
                "no_op_transition",
                f"Tenant is already in '{target_status}' status.",
            )

        # ------------------------------------------------------------------
        # Step 4 — Transition matrix check (rollback; no audit log written)
        # ------------------------------------------------------------------
        if not _ALLOWED_TRANSITIONS.get((current_status, target_status), False):
            db.rollback()
            raise TenantAPIError(
                422,
                "forbidden_transition",
                f"Transition from '{current_status}' to '{target_status}' is not permitted.",
            )

        # ------------------------------------------------------------------
        # Step 5 — status_reason validation
        # ------------------------------------------------------------------
        new_reason: str | None
        if target_status in ("suspended", "archived"):
            sr = command.status_reason
            if sr is None or not sr.strip():
                db.rollback()
                raise TenantAPIError(
                    422,
                    "missing_status_reason",
                    f"status_reason is required when transitioning to '{target_status}' status.",
                    [{"field": "status_reason", "reason": "missing_status_reason"}],
                )
            trimmed = sr.strip()
            if len(trimmed) < 10:
                db.rollback()
                raise TenantAPIError(
                    422,
                    "validation_error",
                    "status_reason must be at least 10 characters.",
                    [{"field": "status_reason", "reason": "min_length"}],
                )
            if len(trimmed) > 500:
                db.rollback()
                raise TenantAPIError(
                    422,
                    "validation_error",
                    "status_reason must not exceed 500 characters.",
                    [{"field": "status_reason", "reason": "max_length"}],
                )
            if re.search(r"[\x00-\x1F\x7F]", trimmed):
                db.rollback()
                raise TenantAPIError(
                    422,
                    "validation_error",
                    "status_reason contains invalid control characters.",
                    [{"field": "status_reason", "reason": "invalid_characters"}],
                )
            new_reason = trimmed
        else:
            # Transitioning to active or draft: auto-clear status_reason (TDD §4.4 §6.6)
            new_reason = None

        # ------------------------------------------------------------------
        # Step 6 — Atomic write: UPDATE tenant + INSERT audit + INSERT outbox
        # ------------------------------------------------------------------
        log_id = str(uuid.uuid4())
        occurred_at = datetime.now(UTC)

        previous_data = {
            "status": current_status,
            "status_reason": row["status_reason"],
        }
        new_data_dict = {
            "status": target_status,
            "status_reason": new_reason,
        }

        try:
            updated = TenantRepository.update_status(
                db,
                tenant_id_str=command.tenant_id,
                new_status=target_status,
                new_reason=new_reason,
                updated_by=str(command.actor_id),
            )

            AuditLogRepository.insert_status_change(
                db,
                log_id=log_id,
                tenant_id=command.tenant_id,
                actor_id=str(command.actor_id),
                actor_role=command.actor_role,
                previous_data=previous_data,
                new_data=new_data_dict,
                reason=new_reason,
            )

            if target_status == "suspended":
                OutboxRepository.insert_suspended_event(
                    db,
                    event_id=str(uuid.uuid4()),
                    tenant_id=command.tenant_id,
                    occurred_at=occurred_at,
                )

                # Cascade-suspend all active workspaces in the same transaction.
                tenant_uuid = uuid.UUID(command.tenant_id)
                suspended_ws_ids = _WorkspaceRepository().bulk_suspend_by_tenant(
                    db,
                    tenant_id=tenant_uuid,
                    status_reason=new_reason or "Tenant suspended.",
                    updated_by=command.actor_id,
                    now=occurred_at,
                )
                if suspended_ws_ids:
                    logger.info(
                        "cascade-suspended %d workspace(s) for tenant %s: %s",
                        len(suspended_ws_ids),
                        command.tenant_id,
                        suspended_ws_ids,
                    )

            # When a tenant is reactivated from a suspended state, restore all
            # workspaces that were cascade-suspended back to 'active'.
            if target_status == "active" and current_status == "suspended":
                tenant_uuid = uuid.UUID(command.tenant_id)
                activated_ws_ids = _WorkspaceRepository().bulk_activate_by_tenant(
                    db,
                    tenant_id=tenant_uuid,
                    updated_by=command.actor_id,
                    now=occurred_at,
                )
                if activated_ws_ids:
                    logger.info(
                        "cascade-activated %d workspace(s) for tenant %s: %s",
                        len(activated_ws_ids),
                        command.tenant_id,
                        activated_ws_ids,
                    )

            # When a tenant is archived, cascade-archive all its workspaces
            # in the same transaction so the data stays consistent.
            if target_status == "archived":
                tenant_uuid = uuid.UUID(command.tenant_id)
                archived_ws_ids = _WorkspaceRepository().bulk_archive_by_tenant(
                    db,
                    tenant_id=tenant_uuid,
                    status_reason=new_reason or "Tenant archived.",
                    updated_by=command.actor_id,
                    now=occurred_at,
                )
                if archived_ws_ids:
                    logger.info(
                        "cascade-archived %d workspace(s) for tenant %s: %s",
                        len(archived_ws_ids),
                        command.tenant_id,
                        archived_ws_ids,
                    )

            # Step 7 — Commit (releases the FOR UPDATE lock)
            db.commit()

        except TenantAPIError:
            db.rollback()
            raise

        except Exception:
            db.rollback()
            logger.exception("Unexpected error during tenant status change")
            raise TenantAPIError(500, "internal_error", "An unexpected error occurred.")

        # ------------------------------------------------------------------
        # Step 8 — Fire-and-forget metric; build and return DTO
        # ------------------------------------------------------------------
        try:
            emit_tenant_status_change(
                from_status=current_status,
                to_status=target_status,
            )
        except Exception:
            logger.exception("Metric emission failed (non-fatal); request unaffected")

        return ChangeStatusDTO(
            tenant_id=str(updated["tenant_id"]),
            previous_status=current_status,
            current_status=str(updated["status"]),
            status_reason=updated["status_reason"],
            updated_at=updated["updated_at"],
            updated_by=str(updated["updated_by"]),
        )

    @staticmethod
    def hard_delete(db: Session, tenant_id: str, actor_id: str) -> None:
        """Permanently remove a tenant and every dependent row.

        Restricted to platform_admin (enforced at the route layer).  All
        deletes run inside a single transaction; FK enforcement is
        temporarily disabled (``session_replication_role = 'replica'``) so
        the cleanup does not have to follow a hand-maintained topological
        order.  The session role is restored regardless of outcome.

        Raises:
            TenantAPIError(404): Tenant not found.
            TenantAPIError(500): Unexpected error.
        """
        # Verify existence first
        row = TenantRepository.find_by_id(db, tenant_id)
        if row is None:
            raise TenantAPIError(404, "not_found", "Tenant not found.")

        # Tables we must NEVER touch (would wipe out platform-level state).
        # public.users carries a nullable tenant_id but represents people who
        # may be platform-only or attached to other tenants; we leave them.
        skip_tables = {
            ("control", "tenants"),
            ("public", "users"),
        }

        try:
            # Disable FK enforcement for the duration of this transaction so
            # the order of deletes does not matter and orphaning is impossible.
            db.execute(text("SET LOCAL session_replication_role = 'replica'"))

            # ── Step 1: snapshot workspace_ids for this tenant ───────────
            ws_rows = db.execute(
                text(
                    "SELECT workspace_id::text FROM control.workspaces "
                    "WHERE tenant_id = CAST(:tid AS UUID)"
                ),
                {"tid": tenant_id},
            ).fetchall()
            workspace_ids = [r[0] for r in ws_rows]

            # ── Step 2: delete every row referencing those workspace_ids ─
            # across both schemas, regardless of whether the table also
            # carries a tenant_id column.
            if workspace_ids:
                ws_ref_tables = db.execute(
                    text(
                        "SELECT table_schema, table_name "
                        "FROM information_schema.columns "
                        "WHERE column_name = 'workspace_id' "
                        "AND table_schema IN ('control', 'public')"
                    )
                ).fetchall()
                for schema, tbl in ws_ref_tables:
                    if (schema, tbl) in skip_tables:
                        continue
                    db.execute(
                        text(
                            f'DELETE FROM "{schema}"."{tbl}" '
                            f"WHERE workspace_id = ANY(CAST(:ids AS UUID[]))"
                        ),
                        {"ids": workspace_ids},
                    )

            # ── Step 3: delete every row carrying this tenant_id across
            # both schemas (catches outbox_events, metadata_term_index, etc.)
            tenant_ref_tables = db.execute(
                text(
                    "SELECT table_schema, table_name "
                    "FROM information_schema.columns "
                    "WHERE column_name = 'tenant_id' "
                    "AND table_schema IN ('control', 'public')"
                )
            ).fetchall()
            for schema, tbl in tenant_ref_tables:
                if (schema, tbl) in skip_tables:
                    continue
                db.execute(
                    text(f'DELETE FROM "{schema}"."{tbl}" WHERE tenant_id = CAST(:tid AS UUID)'),
                    {"tid": tenant_id},
                )

            # ── Step 4: finally remove the tenant row itself ─────────────
            db.execute(
                text("DELETE FROM control.tenants WHERE tenant_id = CAST(:tid AS UUID)"),
                {"tid": tenant_id},
            )

            db.commit()
        except TenantAPIError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            logger.exception("Unexpected error during tenant hard delete")
            raise TenantAPIError(500, "internal_error", "An unexpected error occurred.")

        logger.info(
            "tenant %s hard-deleted by actor %s (workspaces=%d)",
            tenant_id,
            actor_id,
            len(workspace_ids),
        )


# ---------------------------------------------------------------------------
# Module-level helpers (not part of TenantService — avoids cluttering the class)
# ---------------------------------------------------------------------------


def _safe_registry_call(client: Any, tenant_id: str, registry_name: str) -> tuple[int, bool]:
    """Call ``client.get_count(tenant_id)`` and return ``(count, available)``.

    Always returns a 2-tuple; never raises.  On any exception the count is
    returned as ``0`` and ``available`` as ``False``, and a WARN-level log
    entry is emitted (TDD §3.4).
    """
    try:
        count = client.get_count(tenant_id)
        return count, True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Registry '%s' call failed for tenant %s: %s — returning count=0, available=False",
            registry_name,
            tenant_id,
            exc,
        )
        return 0, False


def _to_audit_value(value: Any) -> Any:
    """Convert a field value to a JSON-serialisable form for audit payloads.

    ``date`` objects are serialised as ISO-8601 strings; all other types
    pass through unchanged.
    """
    if isinstance(value, date):
        return value.isoformat()
    return value


def _build_change_set(
    provided_fields: dict[str, Any],
    current_row: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compare provided fields against current DB values and build the change set.

    Args:
        provided_fields: {field_name: validated_new_value} — only keys that
                         were explicitly in the PATCH body.
        current_row:     Full DB row returned by ``find_by_id_for_update``.

    Returns:
        A 3-tuple of plain dicts: ``(changes, previous_data, new_data)``
        where each dict contains only the fields that actually changed.
        ``previous_data`` and ``new_data`` use JSON-serialisable values
        (dates converted to ISO strings) as required by the audit log schema.
    """
    changes: dict[str, Any] = {}
    previous_data: dict[str, Any] = {}
    new_data: dict[str, Any] = {}

    for field, new_value in provided_fields.items():
        current_value = current_row.get(field)
        if new_value != current_value:
            changes[field] = new_value
            previous_data[field] = _to_audit_value(current_value)
            new_data[field] = _to_audit_value(new_value)

    return changes, previous_data, new_data
