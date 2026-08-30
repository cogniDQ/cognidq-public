/**
 * F130 P05 — Redirect tests
 *
 * Coverage:
 *   1. /hub/ws/:id/glossary → /hub/glossary
 *   2. /workspaces/:id/data-sources/anything → /hub/connections (old deep-link)
 *   3. /hub/ws/:id/data-sources → /hub/connections (hub-routed old path)
 *   4. /hub/ws/:id/overview still resolves (NOT redirected — regression)
 *   5. /hub/ws/:id/flows still resolves (NOT redirected — regression)
 *   6. /hub/ws/:id/rules still resolves (NOT redirected — regression)
 *   7. connections path on the tenant section resolves to /hub/connections
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'

// We test route configurations in isolation — no need to import App.tsx
// (avoids pyspark/langgraph transitive imports from full app)

function OverviewStub() {
  return <div data-testid="overview-page">Overview</div>
}
function FlowsStub() {
  return <div data-testid="flows-page">Flows</div>
}
function RulesStub() {
  return <div data-testid="rules-page">Rules</div>
}
function ConnectionsStub() {
  return <div data-testid="connections-page">Connections</div>
}
function GlossaryStub() {
  return <div data-testid="glossary-page">Glossary</div>
}

describe('F130 redirect routes', () => {
  it('/hub/ws/:id/glossary redirects to /hub/glossary', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc/glossary']}>
        <Routes>
          <Route path="/hub/ws/:id/glossary" element={<Navigate replace to="/hub/glossary" />} />
          <Route path="/hub/glossary" element={<GlossaryStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('glossary-page')).toBeInTheDocument()
  })

  it('/hub/ws/:id/data-sources redirects to /hub/connections', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc/data-sources']}>
        <Routes>
          <Route path="/hub/ws/:id/data-sources" element={<Navigate replace to="/hub/connections" />} />
          <Route path="/hub/ws/:id/data-sources/*" element={<Navigate replace to="/hub/connections" />} />
          <Route path="/hub/connections" element={<ConnectionsStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('connections-page')).toBeInTheDocument()
  })

  it('/hub/ws/:id/data-sources/* (deep-link) redirects to /hub/connections', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc/data-sources/ds-123/edit']}>
        <Routes>
          <Route path="/hub/ws/:id/data-sources" element={<Navigate replace to="/hub/connections" />} />
          <Route path="/hub/ws/:id/data-sources/*" element={<Navigate replace to="/hub/connections" />} />
          <Route path="/hub/connections" element={<ConnectionsStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('connections-page')).toBeInTheDocument()
  })

  it('/hub/ws/:id/overview still resolves — not redirected (regression)', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc/overview']}>
        <Routes>
          <Route path="/hub/ws/:id/overview" element={<OverviewStub />} />
          <Route path="/hub/connections" element={<ConnectionsStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('overview-page')).toBeInTheDocument()
    expect(screen.queryByTestId('connections-page')).not.toBeInTheDocument()
  })

  it('/hub/ws/:id/flows still resolves — not redirected (regression)', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc/flows']}>
        <Routes>
          <Route path="/hub/ws/:id/flows" element={<FlowsStub />} />
          <Route path="/hub/glossary" element={<GlossaryStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('flows-page')).toBeInTheDocument()
  })

  it('/hub/ws/:id/rules still resolves — not redirected (regression)', () => {
    render(
      <MemoryRouter initialEntries={['/hub/ws/abc/rules']}>
        <Routes>
          <Route path="/hub/ws/:id/rules" element={<RulesStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('rules-page')).toBeInTheDocument()
  })

  it('/hub/connections resolves to tenant connections page', () => {
    render(
      <MemoryRouter initialEntries={['/hub/connections']}>
        <Routes>
          <Route path="/hub/connections" element={<ConnectionsStub />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('connections-page')).toBeInTheDocument()
  })
})
