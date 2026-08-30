/**
 * WorkspaceContext — F077 P02
 *
 * Provides the currently selected workspace to the DQ Hub.
 * The selected workspace ID is persisted in localStorage so it
 * survives page reloads.
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { listWorkspaces, type WorkspaceSummary, type WorkspaceDetail } from '../services/workspace';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface WorkspaceContextValue {
  currentWorkspace: WorkspaceSummary | null;
  workspaces: WorkspaceSummary[];
  switchWorkspace: (id: string) => void;
  loading: boolean;
  /** Full workspace detail for the currently active workspace, if fetched. */
  currentWorkspaceDetail: WorkspaceDetail | null;
  /** Set the full detail for the active workspace (called by WorkspaceAccessGuard). */
  setCurrentWorkspaceDetail: (detail: WorkspaceDetail | null) => void;
  /**
   * The tenant_id of the currently active workspace.
   * Derived from currentWorkspaceDetail when available, otherwise null.
   */
  currentTenantId: string | null;
}

const STORAGE_KEY = 'selected_workspace_id';

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

// ─────────────────────────────────────────────────────────────────────────────
// Provider
// ─────────────────────────────────────────────────────────────────────────────

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY),
  );
  const [loading, setLoading] = useState(true);
  const [currentWorkspaceDetail, setCurrentWorkspaceDetailState] = useState<WorkspaceDetail | null>(null);

  const setCurrentWorkspaceDetail = useCallback((detail: WorkspaceDetail | null) => {
    setCurrentWorkspaceDetailState(detail);
    if (detail) {
      setSelectedId(detail.workspace_id);
      localStorage.setItem(STORAGE_KEY, detail.workspace_id);
    }
  }, []);

  // Fetch workspace list on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await listWorkspaces({ page_size: 100 });
        if (cancelled) return;
        const active = resp.data.filter((w) => w.status === 'active');
        setWorkspaces(active);

        // Auto-select first workspace only when NOTHING is stored yet.
        // Do NOT override when a workspace ID is already saved: it may be a
        // cross-tenant workspace (e.g. platform admin browsing another tenant)
        // that isn't present in this user's own workspace list.
        if (active.length > 0) {
          const saved = localStorage.getItem(STORAGE_KEY);
          if (!saved) {
            const first = active[0].workspace_id;
            setSelectedId(first);
            localStorage.setItem(STORAGE_KEY, first);
          }
        }
      } catch (err) {
        console.error('Failed to load workspaces:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const switchWorkspace = useCallback((id: string) => {
    setSelectedId(id);
    localStorage.setItem(STORAGE_KEY, id);
    // Clear the stored detail when switching — it will be re-fetched by WorkspaceAccessGuard
    setCurrentWorkspaceDetailState(null);
  }, []);

  // currentWorkspace: prefer the workspace list entry; fall back to a summary
  // synthesised from the detail (handles cross-tenant workspaces not in the list).
  const listMatch = workspaces.find((w) => w.workspace_id === selectedId) ?? null;
  const detailAsSummary: WorkspaceSummary | null =
    currentWorkspaceDetail && currentWorkspaceDetail.workspace_id === selectedId
      ? {
          workspace_id: currentWorkspaceDetail.workspace_id,
          tenant_id: currentWorkspaceDetail.tenant_id,
          tenant_name: currentWorkspaceDetail.tenant_name ?? null,
          workspace_name: currentWorkspaceDetail.workspace_name,
          workspace_slug: currentWorkspaceDetail.workspace_slug,
          status: currentWorkspaceDetail.status,
          default_timezone: currentWorkspaceDetail.default_timezone,
          created_at: currentWorkspaceDetail.created_at,
          updated_at: currentWorkspaceDetail.updated_at,
        }
      : null;
  const currentWorkspace = listMatch ?? detailAsSummary;

  const currentTenantId = currentWorkspaceDetail?.tenant_id ?? null;

  return (
    <WorkspaceContext.Provider value={{ currentWorkspace, workspaces, switchWorkspace, loading, currentWorkspaceDetail, setCurrentWorkspaceDetail, currentTenantId }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within <WorkspaceProvider>');
  return ctx;
}
