import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import AdminRedirect from '@/components/AdminRedirect'

function renderWithRoute(initialPath: string) {
  let navigatedTo = ''
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/hub/admin/*" element={<AdminRedirect />} />
        <Route path="*" element={<CaptureLocation onCapture={(p) => { navigatedTo = p }} />} />
      </Routes>
    </MemoryRouter>
  )
  return navigatedTo
}

function CaptureLocation({ onCapture }: { onCapture: (path: string) => void }) {
  const { pathname } = useLocation()
  onCapture(pathname)
  return null
}

describe('AdminRedirect', () => {
  it('redirects /hub/admin/tenants to /admin/tenants', () => {
    const target = renderWithRoute('/hub/admin/tenants')
    expect(target).toBe('/admin/tenants')
  })

  it('redirects /hub/admin/tenants/new to /admin/tenants/new', () => {
    const target = renderWithRoute('/hub/admin/tenants/new')
    expect(target).toBe('/admin/tenants/new')
  })

  it('redirects /hub/admin with empty splat to /admin/', () => {
    const target = renderWithRoute('/hub/admin')
    expect(target).toBe('/admin/')
  })
})
