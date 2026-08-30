/**
 * ConnectionListPage — unit tests — F132 P02 (BUG-005)
 *
 * Verifies that the Name column renders source_name from the API
 * and that each row link points to /hub/connections/{connection_id}.
 *
 * Test IDs: T02-01 through T02-05
 */
import { render, screen } from '@testing-library/react'
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
  useWorkspace: vi.fn(() => ({ currentTenantId: 'tenant-uuid-001' })),
}))

import { listConnections } from '@/services/connectionService'
import { getTenantId, getActorRole } from '@/utils/jwt'

const mockListConnections = listConnections as ReturnType<typeof vi.fn>
const mockGetTenantId = getTenantId as ReturnType<typeof vi.fn>
const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>

const TENANT_ID = 'tenant-uuid-001'

const sampleConnections = [
  {
    connection_id: 'conn-001',
    tenant_id: TENANT_ID,
    source_name: 'Production Postgres',
    source_type: 'postgresql',
    connection_mode: 'read_only' as const,
    environment: 'production' as const,
    description: null,
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    connection_id: 'conn-002',
    tenant_id: TENANT_ID,
    source_name: 'Staging MySQL',
    source_type: 'mysql',
    connection_mode: 'read_write' as const,
    environment: 'staging' as const,
    description: null,
    status: 'inactive',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ConnectionListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ConnectionListPage — Name column (F132 P02)', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-token')
    mockGetTenantId.mockReturnValue(TENANT_ID)
    mockGetActorRole.mockReturnValue('workspace_user')
    mockListConnections.mockResolvedValue({ items: sampleConnections, total: 2, page: 1, page_size: 20 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // T02-01: source_name text is rendered in the Name column
  it('T02-01: renders source_name text in the Name cell', async () => {
    renderPage()
    const nameLink = await screen.findByText('Production Postgres')
    expect(nameLink).not.toBeNull()
  })

  // T02-02: both rows render their source_name
  it('T02-02: renders all connection names from the list', async () => {
    renderPage()
    expect(await screen.findByText('Production Postgres')).not.toBeNull()
    expect(await screen.findByText('Staging MySQL')).not.toBeNull()
  })

  // T02-03: Name cell contains an anchor pointing to the connection detail route
  it('T02-03: Name link href points to /hub/t/{tenantId}/connections/{connection_id}', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: 'Production Postgres' })
    expect(link.getAttribute('href')).toBe('/hub/t/tenant-uuid-001/connections/conn-001')
  })

  // T02-04: Empty state shown when no connections returned
  it('T02-04: shows empty state when no connections exist', async () => {
    mockListConnections.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    renderPage()
    expect(await screen.findByTestId('empty-state')).not.toBeNull()
  })

  // T02-05: Add Connection button visible only to admin roles
  it('T02-05: Add Connection button is shown for tenant_admin', async () => {
    mockGetActorRole.mockReturnValue('tenant_admin')
    renderPage()
    expect(await screen.findByTestId('add-connection-btn')).not.toBeNull()
  })
})
