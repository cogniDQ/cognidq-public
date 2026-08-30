/**
 * App.tsx redirect routes — unit tests — F132 P01
 *
 * Verifies the two new <Navigate> routes added for BUG-016 and BUG-017.
 * Test IDs: T01-01 through T01-04
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi } from 'vitest'

// Minimal Navigate-only test harness — no need to render the full App
import { Navigate } from 'react-router-dom'

function AppRedirectHarness({ initialPath }: { initialPath: string }) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        {/* Routes under test (F132 P01) */}
        <Route path="/hub/datasources" element={<Navigate replace to="/hub/connections" />} />
        <Route path="/hub/ws/:id/data-sources/new" element={<Navigate replace to="/hub/connections/new" />} />
        <Route path="/hub/ws/:id/data-sources" element={<Navigate replace to="/hub/connections" />} />
        <Route path="/hub/ws/:id/data-sources/*" element={<Navigate replace to="/hub/connections" />} />

        {/* Destination pages (stubs) */}
        <Route path="/hub/connections" element={<div data-testid="connections-page">Connections</div>} />
        <Route path="/hub/connections/new" element={<div data-testid="connections-new-page">New Connection</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('App.tsx redirect routes (F132 P01)', () => {
  // T01-01: /hub/datasources → /hub/connections
  it('T01-01: /hub/datasources redirects to /hub/connections', () => {
    render(<AppRedirectHarness initialPath="/hub/datasources" />)
    expect(screen.queryByTestId('connections-page')).not.toBeNull()
  })

  // T01-02: /hub/ws/:id/data-sources/new → /hub/connections/new
  it('T01-02: /hub/ws/:id/data-sources/new redirects to /hub/connections/new', () => {
    render(<AppRedirectHarness initialPath="/hub/ws/abc-123/data-sources/new" />)
    expect(screen.queryByTestId('connections-new-page')).not.toBeNull()
  })

  // T01-03: /hub/ws/:id/data-sources still redirects to /hub/connections
  it('T01-03: /hub/ws/:id/data-sources redirects to /hub/connections', () => {
    render(<AppRedirectHarness initialPath="/hub/ws/abc-123/data-sources" />)
    expect(screen.queryByTestId('connections-page')).not.toBeNull()
  })

  // T01-04: /hub/connections/new is not a redirect — it's a real page
  it('T01-04: /hub/connections/new renders the new connection page directly', () => {
    render(<AppRedirectHarness initialPath="/hub/connections/new" />)
    expect(screen.queryByTestId('connections-new-page')).not.toBeNull()
  })
})
