/**
 * F130 P04 — ConnectionDetailPage tests
 *
 * Coverage:
 *   1. Renders connection fields from mocked API response
 *   2. WorkspaceAssignmentPanel visible for tenant_admin
 *   3. WorkspaceAssignmentPanel hidden for non-admin
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import ConnectionDetailPage from '@/pages/connections/ConnectionDetailPage'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('@/services/connectionService', () => ({
  getConnection: vi.fn(),
  deleteConnection: vi.fn(),
  testConnection: vi.fn(),
  getConnectionAssignments: vi.fn(),
}))

vi.mock('@/utils/jwt', () => ({
  getTenantId: vi.fn(),
  getActorRole: vi.fn(),
}))

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(() => ({ currentTenantId: 'tenant-123' })),
}))

// Shallow mock WorkspaceAssignmentPanel
vi.mock('@/components/connections/WorkspaceAssignmentPanel', () => ({
  default: () => <div data-testid="workspace-assignment-panel">Assignments</div>,
}))

import { getConnection, getConnectionAssignments } from '@/services/connectionService'
import { getTenantId, getActorRole } from '@/utils/jwt'

const mockGetConnection = getConnection as ReturnType<typeof vi.fn>
const mockGetAssignments = getConnectionAssignments as ReturnType<typeof vi.fn>
const mockGetTenantId = getTenantId as ReturnType<typeof vi.fn>
const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>

const MOCK_CONNECTION = {
  connection_id: 'conn-1',
  tenant_id: 'tenant-123',
  name: 'Prod DB',
  source_type: 'postgresql',
  connection_mode: 'read_only',
  environment: 'production',
  status: 'active',
  description: 'Main production database',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
}

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage(role = 'workspace_member') {
  mockGetTenantId.mockReturnValue('tenant-123')
  mockGetActorRole.mockReturnValue(role)
  mockGetConnection.mockResolvedValue(MOCK_CONNECTION)
  mockGetAssignments.mockResolvedValue([])

  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/hub/connections/conn-1']}>
        <Routes>
          <Route path="/hub/connections/:connection_id" element={<ConnectionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ConnectionDetailPage', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock_token')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders connection fields from mocked API response', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Prod DB')).toBeInTheDocument()
    })
    expect(screen.getByTestId('field-source-type')).toHaveTextContent('postgresql')
    expect(screen.getByTestId('field-environment')).toHaveTextContent('production')
    expect(screen.getByTestId('field-status')).toHaveTextContent('active')
  })

  it('shows WorkspaceAssignmentPanel for tenant_admin', async () => {
    renderPage('tenant_admin')
    await waitFor(() => {
      expect(screen.getByTestId('workspace-assignment-panel')).toBeInTheDocument()
    })
  })

  it('hides WorkspaceAssignmentPanel for non-admin', async () => {
    renderPage('workspace_member')
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-assignment-panel')).not.toBeInTheDocument()
    })
  })
})
