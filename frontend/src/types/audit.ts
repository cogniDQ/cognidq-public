/**
 * F008 — Permission Audit Visibility — TypeScript types
 *
 * Interfaces mirror the Pydantic response models in
 * backend/app/schemas/permission_audit.py (PermissionAuditEntry + PermissionAuditPage).
 *
 * NOTE: source_ip, previous_data, new_data are intentionally absent — the API
 * never returns those fields and the frontend must not reference them.
 */

export interface PermissionAuditEntry {
  log_id: string;
  occurred_at: string;           // ISO-8601 timestamp string
  action_type: string;
  actor_id: string | null;
  actor_display_name: string | null;
  actor_role: string;
  actor_type: string;            // 'user' | 'system'
  target_entity_type: string | null;
  target_entity_id: string | null;
  target_display_name: string | null;
  workspace_id: string | null;
  request_id: string | null;
}

export interface PermissionAuditPage {
  items: PermissionAuditEntry[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}
