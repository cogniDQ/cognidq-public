/**
 * WorkspaceOverview — unit tests — F132 P03 (BUG-009 + BUG-010)
 *
 * Verifies that tile hrefs have been updated to Phase B paths.
 *
 * Test IDs: T03-01 through T03-05
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import WorkspaceOverview from '@/pages/WorkspaceOverview'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: vi.fn(),
}))

vi.mock('@/services/reportingService', () => ({
  default: {
    getWorkspaceStats: vi.fn().mockResolvedValue({
      datasource_count: 5,
      glossary_count: 12,
      flow_count: 3,
      rule_count: 7,
    }),
  },
}))

import { useWorkspace } from '@/contexts/WorkspaceContext'
const mockUseWorkspace = useWorkspace as ReturnType<typeof vi.fn>

const WS_ID = 'ws-abc-123'

function renderOverview(wsId = WS_ID) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/hub/ws/${wsId}/overview`]}>
        <Routes>
          <Route
            path="/hub/ws/:workspace_id/overview"
            element={<WorkspaceOverview />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WorkspaceOverview tiles (F132 P03)', () => {
  beforeEach(() => {
    mockUseWorkspace.mockReturnValue({
      currentWorkspace: { workspace_id: WS_ID, workspace_name: 'Demo WS' },
      workspaces: [],
      loading: false,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // T03-01: Connections tile points to /hub/connections (not workspace-scoped)
  it('T03-01: Connections tile href is /hub/connections', async () => {
    renderOverview()
    const link = await screen.findByRole('link', { name: /connections/i })
    expect(link.getAttribute('href')).toBe('/hub/connections')
  })

  // T03-02: Glossary tile points to the workspace-scoped /hub/ws/{id}/glossary
  it('T03-02: Glossary tile href is /hub/ws/{workspace_id}/glossary', async () => {
    renderOverview()
    const link = await screen.findByRole('link', { name: /glossary/i })
    expect(link.getAttribute('href')).toBe(`/hub/ws/${WS_ID}/glossary`)
  })

  // T03-03: Flows tile points to /hub/ws/{id}/flows
  it('T03-03: Flows tile href is /hub/ws/{workspace_id}/flows', async () => {
    renderOverview()
    const link = await screen.findByRole('link', { name: /flows/i })
    expect(link.getAttribute('href')).toBe(`/hub/ws/${WS_ID}/flows`)
  })

  // T03-04: No tile uses the legacy /data-sources or /flow-builder paths
  it('T03-04: no tile references legacy data-sources or flow-builder paths', async () => {
    const { container } = renderOverview()
    // Wait for component to render tiles
    await screen.findByRole('link', { name: /connections/i })
    const links = Array.from(container.querySelectorAll('a[href]'))
    const hrefs = links.map((a) => a.getAttribute('href') ?? '')
    expect(hrefs.some((h) => h.includes('data-sources'))).toBe(false)
    expect(hrefs.some((h) => h.includes('flow-builder'))).toBe(false)
  })

  // T03-05: Tile titles are updated ('Data Sources' → 'Connections', 'Flow Builder' → 'Flows')
  it('T03-05: tile titles reflect Phase B labels', async () => {
    renderOverview()
    // Phase B heading labels should be present in tile cards (h3 headings)
    expect(await screen.findByRole('heading', { name: /^Connections$/i })).not.toBeNull()
    expect(await screen.findByRole('heading', { name: /^Flows$/i })).not.toBeNull()
    // Legacy tile heading labels should not appear
    expect(screen.queryByRole('heading', { name: /^Data Sources$/i })).toBeNull()
    expect(screen.queryByRole('heading', { name: /^Flow Builder$/i })).toBeNull()
  })
})
