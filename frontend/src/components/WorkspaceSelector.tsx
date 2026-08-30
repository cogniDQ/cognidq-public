/**
 * WorkspaceSelector — F077 P02
 *
 * Dropdown in the DQ Hub sidebar that lets the user switch workspace context.
 * Follows the same visual pattern as the organization selector.
 */
import { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Boxes, ChevronDown } from 'lucide-react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { getTenantId } from '../utils/jwt';
import { wsPath } from '../utils/paths';

interface WorkspaceSelectorProps {
  collapsed: boolean;
}

export default function WorkspaceSelector({ collapsed }: WorkspaceSelectorProps) {
  const { currentWorkspace, workspaces, switchWorkspace, loading } = useWorkspace();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  if (loading) return null;

  return (
    <div ref={ref} className="relative p-3 border-b border-gray-700">
      <button
        onClick={() => setOpen(!open)}
        className={`w-full flex items-center space-x-3 p-2 hover:bg-gray-700 rounded-lg transition-colors ${
          collapsed ? 'justify-center' : ''
        }`}
        title={collapsed ? currentWorkspace?.workspace_name ?? 'Workspace' : ''}
      >
        <Boxes className="w-5 h-5 text-blue-400 flex-shrink-0" />
        {!collapsed && (
          <>
            <span className="text-sm text-white truncate flex-1 text-left">
              {currentWorkspace?.workspace_name ?? 'Select workspace'}
            </span>
            <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
          </>
        )}
      </button>

      {open && !collapsed && (
        <div className="absolute left-3 right-3 mt-2 bg-gray-700 rounded-lg shadow-lg border border-gray-600 z-50 max-h-60 overflow-y-auto">
          {workspaces.map((ws) => (
            <button
              key={ws.workspace_id}
              onClick={() => {
                switchWorkspace(ws.workspace_id);
                setOpen(false);
                // Navigate to the same sub-path but for the new workspace.
                // Match both canonical /hub/t/:tid/ws/:wid/* and legacy /hub/ws/:wid/* URLs.
                const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
                const tenantId = getTenantId(token);
                const tenantWsMatch = location.pathname.match(/^\/hub\/t\/[^/]+\/ws\/[^/]+(\/.*)?$/);
                const flatWsMatch = location.pathname.match(/^\/hub\/ws\/[^/]+(\/.*)?$/);
                if (tenantWsMatch) {
                  const subPath = tenantWsMatch[1] ?? '';
                  navigate(wsPath(tenantId, ws.workspace_id, subPath));
                } else if (flatWsMatch) {
                  const subPath = flatWsMatch[1] ?? '';
                  navigate(wsPath(tenantId, ws.workspace_id, subPath));
                }
              }}
              className={`w-full text-left px-4 py-2 hover:bg-gray-600 first:rounded-t-lg last:rounded-b-lg ${
                ws.workspace_id === currentWorkspace?.workspace_id ? 'bg-gray-600' : ''
              }`}
            >
              <div className="text-sm text-white truncate">{ws.workspace_name}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
