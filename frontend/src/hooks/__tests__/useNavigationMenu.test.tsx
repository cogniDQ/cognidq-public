import { renderHook } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ReactNode } from 'react'
import { useNavigationMenu } from '@/hooks/useNavigationMenu'

// ── Mocks ─────────────────────────────────────────────────────────────────

vi.mock('@/utils/jwt', () => ({
  getRealActorRole: vi.fn(),
  getActorRole: vi.fn(),
  getActorId: vi.fn(),
  getTenantId: vi.fn(),
}))

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(),
}))

vi.mock('@/hooks/useWorkspacePermissions', () => ({
  useWorkspacePermissions: vi.fn(),
}))

import { getRealActorRole, getActorId } from '@/utils/jwt'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { useWorkspacePermissions } from '@/hooks/useWorkspacePermissions'

const mockGetRealActorRole = vi.mocked(getRealActorRole)
const mockGetActorId = vi.mocked(getActorId)
const mockUseWorkspace = vi.mocked(useWorkspace)
const mockUseWorkspacePermissions = vi.mocked(useWorkspacePermissions)

// ── Helpers ────────────────────────────────────────────────────────────────

function wrapper(pathname: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[pathname]}>
      <Routes>
        <Route path="*" element={<>{children}</>} />
      </Routes>
    </MemoryRouter>
  )
}

function defaultWorkspacePermissions(permissions: string[] = []) {
  mockUseWorkspacePermissions.mockReturnValue({
    roleName: 'data_steward',
    loading: false,
    can: (p: string) => permissions.includes(p),
  } as any)
}

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  mockGetRealActorRole.mockReturnValue(null)
  mockGetActorId.mockReturnValue(null)
  mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
  mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false } as any)
})

// ── Tests ──────────────────────────────────────────────────────────────────

describe('useNavigationMenu — section visibility', () => {
  it('shows only tenant section when no workspace is active', () => {
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    defaultWorkspacePermissions(['workspaces:read'])
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub/workspaces') })
    const sectionIds = result.current.sections.map((s) => s.id)
    expect(sectionIds).toContain('tenant')
    expect(sectionIds).not.toContain('workspace')
    expect(sectionIds).not.toContain('platform')
  })

  it('shows workspace section when workspace_id is in URL', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'ws1', workspace_name: 'Demo' },
      workspaces: [],
      loading: false,
    } as any)
    // data_steward has executions:read
    mockUseWorkspacePermissions.mockReturnValue({
      roleName: 'data_steward',
      loading: false,
      can: () => true,
    } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub/ws/ws1/flows') })
    const sectionIds = result.current.sections.map((s) => s.id)
    expect(sectionIds).toContain('workspace')
  })

  it('shows platform section for platform_admin', () => {
    mockGetRealActorRole.mockReturnValue('platform_admin')
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub') })
    const sectionIds = result.current.sections.map((s) => s.id)
    expect(sectionIds).toContain('platform')
  })

  it('does NOT show platform section for regular users', () => {
    mockGetRealActorRole.mockReturnValue('member')
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    defaultWorkspacePermissions([])
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub') })
    const sectionIds = result.current.sections.map((s) => s.id)
    expect(sectionIds).not.toContain('platform')
  })
})

describe('useNavigationMenu — workspace_id injection', () => {
  it('replaces :workspace_id placeholder in workspace section item paths', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'abc123', workspace_name: 'Test' },
      workspaces: [],
      loading: false,
    } as any)
    mockUseWorkspacePermissions.mockReturnValue({ roleName: 'data_steward', loading: false, can: () => true } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub/ws/abc123/issues') })
    const wsSection = result.current.sections.find((s) => s.id === 'workspace')
    expect(wsSection).toBeDefined()
    const paths = wsSection!.items.map((i) => i.path)
    paths.forEach((p) => expect(p).not.toContain(':workspace_id'))
    const issuesItem = wsSection!.items.find((i) => i.id === 'issues')
    expect(issuesItem?.path).toBe('/hub/ws/abc123/issues')
  })

  it('uses explicit workspaceId arg over params/context', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'context-ws', workspace_name: 'Context' },
      workspaces: [],
      loading: false,
    } as any)
    mockUseWorkspacePermissions.mockReturnValue({ roleName: 'data_steward', loading: false, can: () => true } as any)
    const { result } = renderHook(() => useNavigationMenu('explicit-ws'), { wrapper: wrapper('/hub/profile') })
    const wsSection = result.current.sections.find((s) => s.id === 'workspace')
    const overviewPath = wsSection?.items.find((i) => i.id === 'overview')?.path
    expect(overviewPath).toBe('/hub/ws/explicit-ws/overview')
  })
})

describe('useNavigationMenu — permission filtering', () => {
  it('hides items requiring permissions the user lacks', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'ws1', workspace_name: 'Demo' },
      workspaces: [],
      loading: false,
    } as any)
    // User has no permissions
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub/ws/ws1/issues') })
    const wsSection = result.current.sections.find((s) => s.id === 'workspace')
    // Overview has no permission requirement → still visible
    const overviewItem = wsSection?.items.find((i) => i.id === 'overview')
    expect(overviewItem).toBeDefined()
    // Issues requires issues:read → should not be visible
    const issuesItem = wsSection?.items.find((i) => i.id === 'issues')
    expect(issuesItem).toBeUndefined()
  })
})

// ── F132 P04 — platform_admin Workspaces link filter (BUG-012) ─────────────

describe('useNavigationMenu — platform_admin Workspaces filter (F132 P04)', () => {
  // T04-01: platform_admin does NOT see Workspaces in the tenant section
  it('T04-01: platform_admin does not see Workspaces item', () => {
    mockGetRealActorRole.mockReturnValue('platform_admin')
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub') })
    const tenantSection = result.current.sections.find((s) => s.id === 'tenant')
    const workspacesItem = tenantSection?.items.find((i) => i.id === 'workspaces')
    expect(workspacesItem).toBeUndefined()
  })

  // T04-02: platform_admin still sees other tenant-admin items (filter is Workspaces-only)
  it('T04-02: platform_admin still sees tenant-admin Connections and Members', () => {
    mockGetRealActorRole.mockReturnValue('platform_admin')
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub') })
    const tenantAdminSection = result.current.sections.find((s) => s.id === 'tenant-admin')
    expect(tenantAdminSection?.items.find((i) => i.id === 'tenant-connections')).toBeDefined()
    expect(tenantAdminSection?.items.find((i) => i.id === 'tenant-members')).toBeDefined()
  })

  // T04-03: platform_viewer still sees Workspaces (filter is platform_admin only)
  it('T04-03: platform_viewer still sees Workspaces item', () => {
    mockGetRealActorRole.mockReturnValue('platform_viewer')
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    mockUseWorkspacePermissions.mockReturnValue({ roleName: null, loading: false, can: () => false } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub') })
    const tenantSection = result.current.sections.find((s) => s.id === 'tenant')
    expect(tenantSection?.items.find((i) => i.id === 'workspaces')).toBeDefined()
  })

  // T04-04: regular workspace user with workspaces:read still sees Workspaces
  it('T04-04: workspace user with workspaces:read sees Workspaces item', () => {
    mockGetRealActorRole.mockReturnValue('workspace_administrator')
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false } as any)
    mockUseWorkspacePermissions.mockReturnValue({
      roleName: 'workspace_administrator',
      loading: false,
      can: () => false,
    } as any)
    const { result } = renderHook(() => useNavigationMenu(), { wrapper: wrapper('/hub') })
    const tenantSection = result.current.sections.find((s) => s.id === 'tenant')
    expect(tenantSection?.items.find((i) => i.id === 'workspaces')).toBeDefined()
  })
})

