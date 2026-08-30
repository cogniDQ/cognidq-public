import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import TenantLanding from '@/pages/TenantLanding'

const mockUseWorkspace = vi.fn()
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => mockUseWorkspace(),
}))

function CaptureLocation({ onCapture }: { onCapture: (path: string) => void }) {
  const { pathname } = useLocation()
  onCapture(pathname)
  return null
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('TenantLanding', () => {
  it('shows empty state when no workspaces', () => {
    mockUseWorkspace.mockReturnValue({ workspaces: [] })
    render(
      <MemoryRouter>
        <TenantLanding />
      </MemoryRouter>
    )
    expect(screen.getByText('No Workspaces')).toBeTruthy()
    expect(screen.getByText('Create Workspace')).toBeTruthy()
  })

  it('renders workspace cards for multiple workspaces', () => {
    mockUseWorkspace.mockReturnValue({
      workspaces: [
        { workspace_id: 'ws-1', workspace_name: 'Alpha', workspace_slug: 'alpha', created_at: '2026-01-01' },
        { workspace_id: 'ws-2', workspace_name: 'Beta', workspace_slug: 'beta', created_at: '2026-02-01' },
      ],
    })
    render(
      <MemoryRouter>
        <TenantLanding />
      </MemoryRouter>
    )
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.getByText('Beta')).toBeTruthy()
  })

  it('navigates to workspace overview on card click', () => {
    mockUseWorkspace.mockReturnValue({
      workspaces: [
        { workspace_id: 'ws-1', workspace_name: 'Alpha', workspace_slug: 'alpha', created_at: '2026-01-01' },
      ],
    })
    let navigatedTo = ''
    render(
      <MemoryRouter initialEntries={['/hub']}>
        <Routes>
          <Route path="/hub" element={<TenantLanding />} />
          <Route path="*" element={<CaptureLocation onCapture={(p) => { navigatedTo = p }} />} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByText('Alpha'))
    expect(navigatedTo).toBe('/hub/ws/ws-1/overview')
  })

  it('navigates to create workspace from empty state', () => {
    mockUseWorkspace.mockReturnValue({ workspaces: [] })
    let navigatedTo = ''
    render(
      <MemoryRouter initialEntries={['/hub']}>
        <Routes>
          <Route path="/hub" element={<TenantLanding />} />
          <Route path="*" element={<CaptureLocation onCapture={(p) => { navigatedTo = p }} />} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByText('Create Workspace'))
    expect(navigatedTo).toBe('/hub/workspaces/new')
  })
})
