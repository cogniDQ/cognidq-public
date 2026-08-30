/**
 * F130 P04 — ConnectionListPage tests
 *
 * Coverage:
 *   1. Renders connection items from mocked response
 *   2. Renders multiple items
 *   3. Shows empty state when no connections
 *   4. "Add Connection" button visible for tenant_admin
 *   5. "Add Connection" button hidden for non-admin
 *   6. Shows loading state
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import ConnectionListPage from '@/pages/connections/ConnectionListPage'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('@/services/connectionService', () => ({
  listConnections: vi.fn(),
}))

vi.mock('@/utils/jwt', () => ({
  getTenantId: vi.fn(),
  getActorRole: vi.fn(),
}))

vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(() => ({ currentTenantId: 'tenant-123' })),
}))

import { listConnections } from '@/services/connectionService'
import { getTenantId, getActorRole } from '@/utils/jwt'

const mockListConnections = listConnections as ReturnType<typeof vi.fn>
const mockGetTenantId = getTenantId as ReturnType<typeof vi.fn>
const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

function renderPage() {
  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/hub/connections']}>
        <ConnectionListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const MOCK_CONNECTIONS = [
  {
    connection_id: 'c1',
    tenant_id: 't1',
    source_name: 'Prod DB',
    source_type: 'postgresql',
    connection_mode: 'read_only',
    environment: 'production',
    status: 'active',
    description: null,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
  {
    connection_id: 'c2',
    tenant_id: 't1',
    source_name: 'Dev DB',
    source_type: 'mysql',
    connection_mode: 'read_write',
    environment: 'development',
    status: 'active',
    description: null,
    created_at: '2025-01-02T00:00:00Z',
    updated_at: '2025-01-02T00:00:00Z',
  },
]

describe('ConnectionListPage', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock_token')
    mockGetTenantId.mockReturnValue('tenant-123')
    mockGetActorRole.mockReturnValue('workspace_member')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders a connection item from mocked API response', async () => {
    mockListConnections.mockResolvedValue({
      items: [MOCK_CONNECTIONS[0]],
      total: 1,
      page: 1,
      page_size: 25,
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Prod DB')).toBeInTheDocument()
    })
    expect(screen.getByText('postgresql')).toBeInTheDocument()
  })

  it('renders multiple connection items', async () => {
    mockListConnections.mockResolvedValue({
      items: MOCK_CONNECTIONS,
      total: 2,
      page: 1,
      page_size: 25,
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getAllByTestId('connection-row')).toHaveLength(2)
    })
  })

  it('shows empty state when no connections returned', async () => {
    mockListConnections.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument()
    })
  })

  it('shows Add Connection button for tenant_admin', async () => {
    mockGetActorRole.mockReturnValue('tenant_admin')
    mockListConnections.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('add-connection-btn')).toBeInTheDocument()
    })
  })

  it('hides Add Connection button for non-admin', async () => {
    mockGetActorRole.mockReturnValue('workspace_member')
    mockListConnections.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
    renderPage()
    await waitFor(() => {
      expect(screen.queryByTestId('add-connection-btn')).not.toBeInTheDocument()
    })
  })

  it('shows loading state initially', () => {
    mockListConnections.mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByText(/loading connections/i)).toBeInTheDocument()
  })
})
