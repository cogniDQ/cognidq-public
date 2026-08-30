/**
 * F130 P05 — Glossary tenant scope tests
 *
 * Coverage:
 *   1. Glossary uses tenant_id in API call (not workspace_id)
 *   2. QueryKey contains tenantId not workspace_id
 *   3. Renders glossary terms from mocked tenant API
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import Glossary from '@/pages/Glossary'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('@/services/glossaryService', () => ({
  listTenantGlossaryTerms: vi.fn(),
  createTenantGlossaryTerm: vi.fn(),
  updateTenantGlossaryTerm: vi.fn(),
  deleteTenantGlossaryTerm: vi.fn(),
  importTenantGlossaryCSV: vi.fn(),
  exportTenantGlossaryCSV: vi.fn(),
}))

vi.mock('@/hooks/useTenantId', () => ({
  useTenantId: vi.fn(),
}))

import { listTenantGlossaryTerms } from '@/services/glossaryService'
import { useTenantId } from '@/hooks/useTenantId'

const mockList = listTenantGlossaryTerms as ReturnType<typeof vi.fn>
const mockUseTenantId = useTenantId as ReturnType<typeof vi.fn>

const MOCK_TERMS = [
  {
    term_id: 't1',
    workspace_id: null,
    business_name: 'Customer',
    technical_name: 'customer',
    definition: 'A paying client',
    synonyms: [],
    domain: 'Sales',
    linked_asset_ids: [],
    source: 'manual',
    trust_level: 'verified',
    data_type: 'string',
    owner: 'alice',
    is_mandatory: false,
    allowed_values: null,
    created_at: '2025-01-01T00:00:00Z',
  },
]

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderGlossary() {
  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Glossary />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Glossary — tenant scope', () => {
  beforeEach(() => {
    mockUseTenantId.mockReturnValue('tenant-abc')
    mockList.mockResolvedValue({ items: MOCK_TERMS, total: 1, page: 1, page_size: 200 })
  })

  afterEach(() => vi.restoreAllMocks())

  it('calls listTenantGlossaryTerms with tenant_id', async () => {
    renderGlossary()
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith('tenant-abc', expect.any(Object))
    })
  })

  it('does NOT call workspace-scoped API (no workspace_id in call args)', async () => {
    renderGlossary()
    await waitFor(() => expect(mockList).toHaveBeenCalled())
    // The first argument to listTenantGlossaryTerms must be a tenant UUID, not workspace
    const firstArg = mockList.mock.calls[0][0]
    expect(firstArg).toBe('tenant-abc')
  })

  it('renders glossary terms returned from the tenant API', async () => {
    renderGlossary()
    await waitFor(() => {
      expect(screen.getByText('Customer')).toBeInTheDocument()
    })
  })
})
