/**
 * ContextHeader
 *
 * Top-bar context indicator for the DQ Hub. Displays:
 *   <Tenant Name>  ›  <Active Workspace>
 *
 * The workspace segment is a clickable dropdown that lets the user switch
 * between any workspace they are assigned to. The list of workspaces is
 * sourced from `WorkspaceContext.workspaces`, which the backend already
 * filters to the workspaces the actor is a member of (or all workspaces in
 * the tenant for tenant_admin / platform operators).
 *
 * If the user only has access to a single workspace (or none), the
 * dropdown chevron is hidden and the workspace name is rendered as plain
 * text.
 */
import { useState, useRef, useEffect, useMemo } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { ChevronRight, ChevronDown, Building2 } from 'lucide-react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { getTenantId } from '../utils/jwt';
import { wsPath } from '../utils/paths';

const WS_PATH_RE = /(^\/hub\/ws\/[^/]+)|(^\/hub\/t\/[^/]+\/ws\/[^/]+)/;

// F11-pill — sessionStorage cache to bridge the gap between a hub
// navigation and the workspace detail finishing its fetch. Without this,
// the pill flashes "My Organization" for a frame on every tenant-scoped
// route change.
const TENANT_NAME_CACHE_KEY = 'cogni:lastTenantName';

function readCachedTenantName(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage.getItem(TENANT_NAME_CACHE_KEY);
  } catch {
    return null;
  }
}

function writeCachedTenantName(name: string | null) {
  if (typeof window === 'undefined' || !name) return;
  try {
    window.sessionStorage.setItem(TENANT_NAME_CACHE_KEY, name);
  } catch {
    /* ignore */
  }
}

export default function ContextHeader() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const params = useParams<{ tenant_id?: string }>();
  const {
    currentWorkspace,
    currentWorkspaceDetail,
    workspaces,
    switchWorkspace,
  } = useWorkspace();

  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const isWorkspacePage = WS_PATH_RE.test(pathname);
  const workspaceName =
    isWorkspacePage && currentWorkspace ? currentWorkspace.workspace_name : null;

  // Resolve the active tenant id from (in order) URL param, current workspace
  // detail, workspace summary list, or JWT claim. Used both as a fallback
  // label and to keep the pill stable across hub navigations.
  const activeTenantId = useMemo(() => {
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    return (
      params.tenant_id ??
      currentWorkspaceDetail?.tenant_id ??
      currentWorkspace?.tenant_id ??
      workspaces.find((w) => w.tenant_id)?.tenant_id ??
      getTenantId(token) ??
      null
    );
  }, [params.tenant_id, currentWorkspaceDetail, currentWorkspace, workspaces]);

  // Tenant name resolution: prefer the active workspace detail's tenant_name,
  // else any workspace summary that carries it, else the sessionStorage
  // cache (avoids "My Organization" flash on navigation), else a short
  // id-based fallback, else "My Organization".
  const tenantName = useMemo(() => {
    if (currentWorkspaceDetail?.tenant_name) return currentWorkspaceDetail.tenant_name;
    const fromCurrent =
      currentWorkspace && (currentWorkspace as { tenant_name?: string }).tenant_name;
    if (fromCurrent) return fromCurrent;
    const fromList = workspaces.find(
      (w) => w.tenant_name && (!activeTenantId || w.tenant_id === activeTenantId),
    )?.tenant_name;
    if (fromList) return fromList;
    const cached = readCachedTenantName();
    if (cached) return cached;
    if (activeTenantId) return `Tenant ${activeTenantId.slice(0, 8)}…`;
    return 'My Organization';
  }, [currentWorkspaceDetail, currentWorkspace, workspaces, activeTenantId]);

  // Persist any real (non-fallback) tenant name so the next navigation
  // can render it instantly while data refetches.
  useEffect(() => {
    if (
      tenantName &&
      tenantName !== 'My Organization' &&
      !tenantName.startsWith('Tenant ')
    ) {
      writeCachedTenantName(tenantName);
    }
  }, [tenantName]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const canSwitch = isWorkspacePage && workspaces.length > 1;

  function handleSelect(workspaceId: string) {
    setOpen(false);
    if (currentWorkspace?.workspace_id === workspaceId) return;
    switchWorkspace(workspaceId);
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const tenantId =
      currentWorkspaceDetail?.tenant_id ??
      workspaces.find((w) => w.workspace_id === workspaceId)?.tenant_id ??
      getTenantId(token);
    const tenantWsMatch = pathname.match(/^\/hub\/t\/[^/]+\/ws\/[^/]+(\/.*)?$/);
    const flatWsMatch = pathname.match(/^\/hub\/ws\/[^/]+(\/.*)?$/);
    const subPath = (tenantWsMatch?.[1] ?? flatWsMatch?.[1]) ?? '/overview';
    navigate(wsPath(tenantId ?? null, workspaceId, subPath));
  }

  return (
    <div ref={ref} className="relative flex items-center space-x-1 text-sm">
      <Building2 className="w-4 h-4 text-gray-400 flex-shrink-0" />
      <span className="text-gray-300 font-medium truncate max-w-[200px]" title={tenantName}>
        {tenantName}
      </span>
      {workspaceName && (
        <>
          <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
          {canSwitch ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="flex items-center space-x-1 px-2 py-1 rounded hover:bg-gray-700 transition-colors"
              aria-haspopup="listbox"
              aria-expanded={open}
              title="Switch workspace"
            >
              <span
                className="text-blue-400 font-medium truncate max-w-[180px]"
                title={workspaceName}
              >
                {workspaceName}
              </span>
              <ChevronDown
                className={`w-4 h-4 text-gray-400 transition-transform ${
                  open ? 'rotate-180' : ''
                }`}
              />
            </button>
          ) : (
            <span
              className="text-blue-400 font-medium truncate max-w-[180px]"
              title={workspaceName}
            >
              {workspaceName}
            </span>
          )}
        </>
      )}

      {open && canSwitch && (
        <div
          role="listbox"
          className="absolute right-0 top-full mt-2 w-64 bg-gray-800 rounded-lg shadow-lg border border-gray-700 z-50 max-h-72 overflow-y-auto"
        >
          {workspaces.map((ws) => {
            const active = ws.workspace_id === currentWorkspace?.workspace_id;
            return (
              <button
                key={ws.workspace_id}
                role="option"
                aria-selected={active}
                onClick={() => handleSelect(ws.workspace_id)}
                className={`w-full text-left px-4 py-2 hover:bg-gray-700 first:rounded-t-lg last:rounded-b-lg ${
                  active ? 'bg-gray-700' : ''
                }`}
              >
                <div className="text-sm text-white truncate">{ws.workspace_name}</div>
                {ws.workspace_slug && (
                  <div className="text-xs text-gray-400 truncate">{ws.workspace_slug}</div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
