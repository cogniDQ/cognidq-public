import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ContextHeader from '@/components/ContextHeader'

const mockUseWorkspace = vi.fn()
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => mockUseWorkspace(),
}))

function renderHeader(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <ContextHeader />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ContextHeader', () => {
  it('always renders a tenant name', () => {
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: false })
    renderHeader('/hub/workspaces')
    // Fallback tenant name is always present
    expect(screen.getByText('My Organization')).toBeTruthy()
  })

  it('renders workspace name on workspace-scoped pages', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'ws1', workspace_name: 'Acme DQ' },
      workspaces: [],
      loading: false,
    })
    renderHeader('/hub/ws/ws1/issues')
    expect(screen.getByText('Acme DQ')).toBeTruthy()
    expect(screen.getByText('My Organization')).toBeTruthy()
  })

  it('does NOT render workspace name on tenant-scoped pages', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'ws1', workspace_name: 'Acme DQ' },
      workspaces: [],
      loading: false,
    })
    renderHeader('/hub/workspaces')
    expect(screen.queryByText('Acme DQ')).toBeNull()
    expect(screen.getByText('My Organization')).toBeTruthy()
  })

  it('does NOT render workspace name on profile page', () => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: 'ws1', workspace_name: 'Acme DQ' },
      workspaces: [],
      loading: false,
    })
    renderHeader('/hub/profile')
    expect(screen.queryByText('Acme DQ')).toBeNull()
  })

  it('does NOT render workspace name when currentWorkspace is null on a ws-path', () => {
    // Edge case: URL has /hub/ws/... but context hasn't resolved yet
    mockUseWorkspace.mockReturnValue({ currentWorkspace: null, workspaces: [], loading: true })
    renderHeader('/hub/ws/ws1/issues')
    expect(screen.queryByText(/Acme/)).toBeNull()
  })
})
