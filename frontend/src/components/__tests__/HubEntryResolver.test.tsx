import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import HubEntryResolver from '@/components/HubEntryResolver'

const mockUseWorkspace = vi.fn()
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => mockUseWorkspace(),
}))

const mockGetActorRole = vi.fn()
const mockGetTenantId = vi.fn()
vi.mock('@/utils/jwt', () => ({
  getActorRole: (token: string | null) => mockGetActorRole(token),
  getTenantId: (token: string | null) => mockGetTenantId(token),
}))

function CaptureLocation({ onCapture }: { onCapture: (path: string) => void }) {
  const { pathname } = useLocation()
  onCapture(pathname)
  return null
}

function renderResolver() {
  let navigatedTo = ''
  render(
    <MemoryRouter initialEntries={['/hub']}>
      <Routes>
        <Route path="/hub" element={<HubEntryResolver />} />
        <Route path="*" element={<CaptureLocation onCapture={(p) => { navigatedTo = p }} />} />
      </Routes>
    </MemoryRouter>
  )
  return navigatedTo
}

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('HubEntryResolver', () => {
  it('shows spinner while loading', () => {
    mockUseWorkspace.mockReturnValue({ workspaces: [], loading: true })
    mockGetActorRole.mockReturnValue(null)
    render(
      <MemoryRouter initialEntries={['/hub']}>
        <Routes>
          <Route path="/hub" element={<HubEntryResolver />} />
        </Routes>
      </MemoryRouter>
    )
    expect(document.querySelector('.animate-spin')).toBeTruthy()
  })

  it('redirects platform_admin to /admin', () => {
    mockUseWorkspace.mockReturnValue({ workspaces: [], loading: false })
    mockGetActorRole.mockReturnValue('platform_admin')
    const target = renderResolver()
    expect(target).toBe('/admin')
  })

  it('redirects platform_viewer to /admin', () => {
    mockUseWorkspace.mockReturnValue({ workspaces: [], loading: false })
    mockGetActorRole.mockReturnValue('platform_viewer')
    const target = renderResolver()
    expect(target).toBe('/admin')
  })

  it('redirects single-workspace user to workspace overview', () => {
    mockUseWorkspace.mockReturnValue({
      workspaces: [{ workspace_id: 'ws-123', workspace_name: 'Test' }],
      loading: false,
    })
    mockGetActorRole.mockReturnValue('tenant_user')
    const target = renderResolver()
    expect(target).toBe('/hub/ws/ws-123/overview')
  })

  it('renders TenantLanding for multi-workspace user', () => {
    mockUseWorkspace.mockReturnValue({
      workspaces: [
        { workspace_id: 'ws-1', workspace_name: 'One', workspace_slug: 'one', created_at: '2026-01-01' },
        { workspace_id: 'ws-2', workspace_name: 'Two', workspace_slug: 'two', created_at: '2026-01-02' },
      ],
      loading: false,
    })
    mockGetActorRole.mockReturnValue('tenant_user')
    render(
      <MemoryRouter initialEntries={['/hub']}>
        <Routes>
          <Route path="/hub" element={<HubEntryResolver />} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Your Workspaces')).toBeTruthy()
  })

  it('renders TenantLanding empty state for zero workspaces', () => {
    mockUseWorkspace.mockReturnValue({ workspaces: [], loading: false })
    mockGetActorRole.mockReturnValue('tenant_user')
    render(
      <MemoryRouter initialEntries={['/hub']}>
        <Routes>
          <Route path="/hub" element={<HubEntryResolver />} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('No Workspaces')).toBeTruthy()
  })
})
