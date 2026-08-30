import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import WorkspaceSelector from '@/components/WorkspaceSelector'

// ── Mocks ─────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockUseWorkspace = vi.fn()
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => mockUseWorkspace(),
}))

// ── Helpers ────────────────────────────────────────────────────────────────

const WS_LIST = [
  { workspace_id: 'ws-a', workspace_name: 'Alpha' },
  { workspace_id: 'ws-b', workspace_name: 'Beta' },
]

function renderSelector(pathname: string) {
  mockUseWorkspace.mockReturnValue({
    currentWorkspace: WS_LIST[0],
    workspaces: WS_LIST,
    switchWorkspace: vi.fn(),
    loading: false,
  })
  render(
    <MemoryRouter initialEntries={[pathname]}>
      <WorkspaceSelector collapsed={false} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  mockNavigate.mockReset()
})

// ── Tests ──────────────────────────────────────────────────────────────────

describe('WorkspaceSelector', () => {
  it('renders current workspace name', () => {
    renderSelector('/hub/ws/ws-a/issues')
    expect(screen.getByText('Alpha')).toBeTruthy()
  })

  it('opens dropdown on button click', () => {
    renderSelector('/hub/ws/ws-a/issues')
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(screen.getByText('Beta')).toBeTruthy()
  })

  it('navigates to same sub-path in new workspace on workspace-scoped page', () => {
    renderSelector('/hub/ws/ws-a/issues')
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    // Click the Beta option
    fireEvent.click(screen.getByText('Beta'))
    expect(mockNavigate).toHaveBeenCalledWith('/hub/ws/ws-b/issues')
  })

  it('does NOT navigate on non-workspace page switch', () => {
    renderSelector('/hub/profile')
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    fireEvent.click(screen.getByText('Beta'))
    // No navigate call — only context switch
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('replaces workspace_id preserving deeper sub-path', () => {
    renderSelector('/hub/ws/ws-a/executions/exec-123')
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    fireEvent.click(screen.getByText('Beta'))
    expect(mockNavigate).toHaveBeenCalledWith('/hub/ws/ws-b/executions/exec-123')
  })
})
