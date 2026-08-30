import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import WorkspaceRedirect from '@/components/WorkspaceRedirect'

function renderWithRoute(initialPath: string, routePath: string, props: { base: string; suffix?: string }) {
  let navigatedTo = ''
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path={routePath} element={<WorkspaceRedirect {...props} />} />
        <Route path="*" element={<CaptureLocation onCapture={(p) => { navigatedTo = p }} />} />
      </Routes>
    </MemoryRouter>
  )
  return navigatedTo
}

function CaptureLocation({ onCapture }: { onCapture: (path: string) => void }) {
  const { pathname, search } = useLocation()
  onCapture(pathname + search)
  return null
}

describe('WorkspaceRedirect', () => {
  it('redirects /workspaces/:id to base/id', () => {
    const target = renderWithRoute(
      '/workspaces/ws-123',
      '/workspaces/:id',
      { base: '/hub/workspaces' }
    )
    expect(target).toBe('/hub/workspaces/ws-123')
  })

  it('redirects with suffix', () => {
    const target = renderWithRoute(
      '/workspaces/ws-123/data-sources',
      '/workspaces/:id/data-sources/*',
      { base: '/hub/ws', suffix: '/data-sources' }
    )
    expect(target).toBe('/hub/ws/ws-123/data-sources')
  })

  it('preserves splat sub-path', () => {
    const target = renderWithRoute(
      '/workspaces/ws-123/data-sources/ds-456/edit',
      '/workspaces/:id/data-sources/*',
      { base: '/hub/ws', suffix: '/data-sources' }
    )
    expect(target).toBe('/hub/ws/ws-123/data-sources/ds-456/edit')
  })

  it('preserves query string', () => {
    const target = renderWithRoute(
      '/workspaces/ws-123/issues?status=open',
      '/workspaces/:id/issues/*',
      { base: '/hub/ws', suffix: '/issues' }
    )
    expect(target).toBe('/hub/ws/ws-123/issues?status=open')
  })
})
