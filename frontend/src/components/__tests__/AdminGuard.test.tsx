/**
 * AdminGuard — unit tests — F129 P05
 *
 * Test coverage per TDD §13:
 *   1. Non-platform user is rejected (ForbiddenPage shown)
 *   2. platform_admin is allowed (children rendered)
 *   3. platform_viewer is allowed (children rendered)
 *   4. Unauthenticated user is redirected to /auth/login
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi } from 'vitest'
import AdminGuard from '@/components/admin/AdminGuard'

// ── Mock AuthContext ──────────────────────────────────────────────────────────
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

// ── Mock jwt utilities ────────────────────────────────────────────────────────
vi.mock('@/utils/jwt', () => ({
  getActorRole: vi.fn(),
}))

import { useAuth } from '@/contexts/AuthContext'
import { getActorRole } from '@/utils/jwt'

const mockUseAuth = useAuth as ReturnType<typeof vi.fn>
const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>

function renderGuard(initialPath = '/admin/tenants') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/admin/*"
          element={
            <AdminGuard>
              <div data-testid="protected-content">Admin Content</div>
            </AdminGuard>
          }
        />
        <Route path="/auth/login" element={<div data-testid="login-page">Login</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AdminGuard', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    mockUseAuth.mockReturnValue({ isAuthenticated: true, loading: false })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders ForbiddenPage for a workspace user (no platform role)', () => {
    mockGetActorRole.mockReturnValue(null)
    renderGuard()
    expect(screen.getByText(/access denied/i)).toBeInTheDocument()
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
  })

  it('allows platform_admin to see protected content', () => {
    mockGetActorRole.mockReturnValue('platform_admin')
    renderGuard()
    expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    expect(screen.queryByText(/access denied/i)).not.toBeInTheDocument()
  })

  it('allows platform_viewer to see protected content', () => {
    mockGetActorRole.mockReturnValue('platform_viewer')
    renderGuard()
    expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    expect(screen.queryByText(/access denied/i)).not.toBeInTheDocument()
  })

  it('redirects unauthenticated user to /auth/login', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, loading: false })
    renderGuard()
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
  })
})
