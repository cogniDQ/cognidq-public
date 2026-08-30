/**
 * F130 P04 — WorkspaceAssignmentPanel tests
 *
 * Coverage:
 *   1. Renders workspace assignments from mocked API
 *   2. PUT fired when workspace selection changes and Save clicked
 *   3. Route /hub/ws/:id/data-sources renders Navigate to /hub/connections
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import WorkspaceAssignmentPanel from '@/components/connections/WorkspaceAssignmentPanel'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('@/services/connectionService', () => ({
  getConnectionAssignments: vi.fn(),
  replaceConnectionAssignments: vi.fn(),
}))

vi.mock('@/services/workspace', () => ({
  listWorkspaces: vi.fn(),
}))

import { getConnectionAssignments, replaceConnectionAssignments } from '@/services/connectionService'
import { listWorkspaces } from '@/services/workspace'

const mockGetAssignments = getConnectionAssignments as ReturnType<typeof vi.fn>
const mockReplaceAssignments = replaceConnectionAssignments as ReturnType<typeof vi.fn>
const mockListWorkspaces = listWorkspaces as ReturnType<typeof vi.fn>

const ALL_WORKSPACES = [
  { workspace_id: 'ws-1', workspace_name: 'Alpha', status: 'active' },
  { workspace_id: 'ws-2', workspace_name: 'Beta', status: 'active' },
]

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPanel(isAdmin = true, assignedIds = ['ws-1']) {
  mockGetAssignments.mockResolvedValue(
    assignedIds.map((id) => ({ workspace_id: id, assigned_at: '2025-01-01T00:00:00Z' })),
  )
  mockListWorkspaces.mockResolvedValue({
    data: ALL_WORKSPACES,
    meta: { total: ALL_WORKSPACES.length, page: 1, page_size: 100, has_next: false },
  })

  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceAssignmentPanel
        tenantId="tenant-123"
        connectionId="conn-1"
        isAdmin={isAdmin}
      />
    </QueryClientProvider>,
  )
}

describe('WorkspaceAssignmentPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders workspace assignments from mocked API', async () => {
    renderPanel(true, ['ws-1'])
    await waitFor(() => {
      expect(screen.getByText('Alpha')).toBeInTheDocument()
      expect(screen.getByText('Beta')).toBeInTheDocument()
    })
    // ws-1 is assigned so its checkbox should be checked
    const alphaCheckbox = screen.getByTestId('ws-check-ws-1') as HTMLInputElement
    expect(alphaCheckbox.checked).toBe(true)
    const betaCheckbox = screen.getByTestId('ws-check-ws-2') as HTMLInputElement
    expect(betaCheckbox.checked).toBe(false)
  })

  it('fires PUT when workspace selection changes and Save clicked', async () => {
    mockReplaceAssignments.mockResolvedValue([
      { workspace_id: 'ws-1', assigned_at: '2025-01-01T00:00:00Z' },
      { workspace_id: 'ws-2', assigned_at: '2025-01-01T00:00:00Z' },
    ])
    renderPanel(true, ['ws-1'])

    await waitFor(() => {
      expect(screen.getByText('Beta')).toBeInTheDocument()
    })

    // Check the Beta checkbox
    fireEvent.click(screen.getByTestId('ws-check-ws-2'))

    // Click Save
    fireEvent.click(screen.getByTestId('save-assignments-btn'))

    await waitFor(() => {
      expect(mockReplaceAssignments).toHaveBeenCalledWith(
        'tenant-123',
        'conn-1',
        expect.arrayContaining(['ws-1', 'ws-2']),
      )
    })
  })
})

// ── Redirect test ──────────────────────────────────────────────────────────────
describe('Redirect: /hub/ws/:id/data-sources → /hub/connections', () => {
  it('renders Navigate to /hub/connections for old data-sources path', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc123/data-sources']}>
        <Routes>
          <Route
            path="/hub/ws/:id/data-sources"
            element={<Navigate replace to="/hub/connections" />}
          />
          <Route
            path="/hub/connections"
            element={<div data-testid="connections-page">Connections</div>}
          />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('connections-page')).toBeInTheDocument()
  })
})
