/**
 * PermissionGate — unit tests — F129 P05
 *
 * Test coverage per TDD §13:
 *   1. Renders children when user has the required permission
 *   2. Renders ForbiddenPage (default fallback) when user lacks the permission
 *   3. Renders custom fallback when provided and permission is absent
 *   4. Platform operators always see children (bypass workspace check)
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import PermissionGate from '@/components/PermissionGate'

// ── Mock jwt utilities ────────────────────────────────────────────────────────
vi.mock('@/utils/jwt', () => ({
  getActorRole: vi.fn(),
  getActorId: vi.fn(),
}))

// ── Mock useWorkspacePermissions ──────────────────────────────────────────────
vi.mock('@/hooks/useWorkspacePermissions', () => ({
  useWorkspacePermissions: vi.fn(),
}))

// ── Mock FIXED_ROLE_PERMISSIONS ───────────────────────────────────────────────
vi.mock('@/services/workspaceRoles', () => ({
  FIXED_ROLE_PERMISSIONS: {
    workspace_administrator: new Set(['view_audit_logs', 'settings:write']),
    data_steward: new Set(['datasets:read']),
  },
}))

import { getActorRole, getActorId } from '@/utils/jwt'
import { useWorkspacePermissions } from '@/hooks/useWorkspacePermissions'

const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>
const mockGetActorId = getActorId as ReturnType<typeof vi.fn>
const mockUseWorkspacePermissions = useWorkspacePermissions as ReturnType<typeof vi.fn>

function wrapper(path: string) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={children} />
        </Routes>
      </MemoryRouter>
    )
  }
}

function renderGate(
  permission: string,
  { path = '/hub/ws/ws1/permission-audit', fallback }: { path?: string; fallback?: React.ReactNode } = {},
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="*"
          element={
            <PermissionGate permission={permission} fallback={fallback}>
              <div data-testid="gate-content">Protected</div>
            </PermissionGate>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PermissionGate', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    mockGetActorRole.mockReturnValue(null)
    mockGetActorId.mockReturnValue('user-1')
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders children when user has the required permission', () => {
    mockUseWorkspacePermissions.mockReturnValue({
      roleName: 'workspace_administrator',
      loading: false,
      can: () => true,
    })
    renderGate('view_audit_logs')
    expect(screen.getByTestId('gate-content')).toBeInTheDocument()
    expect(screen.queryByText(/access denied/i)).not.toBeInTheDocument()
  })

  it('renders ForbiddenPage when user lacks the required permission', () => {
    mockUseWorkspacePermissions.mockReturnValue({
      roleName: 'data_steward',
      loading: false,
      can: () => false,
    })
    renderGate('view_audit_logs')
    expect(screen.getByText(/access denied/i)).toBeInTheDocument()
    expect(screen.queryByTestId('gate-content')).not.toBeInTheDocument()
  })

  it('renders custom fallback when permission is absent and fallback is provided', () => {
    mockUseWorkspacePermissions.mockReturnValue({
      roleName: null,
      loading: false,
      can: () => false,
    })
    renderGate('view_audit_logs', { fallback: <div data-testid="custom-fallback">No Access</div> })
    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument()
    expect(screen.queryByTestId('gate-content')).not.toBeInTheDocument()
  })

  it('always renders children for platform_admin regardless of workspace permissions', () => {
    mockGetActorRole.mockReturnValue('platform_admin')
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false })
    renderGate('view_audit_logs')
    expect(screen.getByTestId('gate-content')).toBeInTheDocument()
    expect(screen.queryByText(/access denied/i)).not.toBeInTheDocument()
  })
})
