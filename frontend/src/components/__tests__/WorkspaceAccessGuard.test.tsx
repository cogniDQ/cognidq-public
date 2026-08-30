/**
 * WorkspaceAccessGuard — unit tests — F131 P03 (RBAC bypass)
 *
 * Test IDs: T03-01 through T03-08
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi } from 'vitest'
import WorkspaceAccessGuard from '@/components/WorkspaceAccessGuard'

// ── Mocks ─────────────────────────────────────────────────────────────────────
vi.mock('@/services/workspace', () => ({
  getWorkspace: vi.fn(),
}))

vi.mock('@/utils/jwt', () => ({
  getActorRole: vi.fn(),
}))

const mockSetCurrentWorkspaceDetail = vi.fn()
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    currentWorkspace: null,
    workspaces: [],
    switchWorkspace: vi.fn(),
    loading: false,
    currentWorkspaceDetail: null,
    setCurrentWorkspaceDetail: mockSetCurrentWorkspaceDetail,
    currentTenantId: null,
  }),
}))

import { getWorkspace } from '@/services/workspace'
import { getActorRole } from '@/utils/jwt'

const mockGetWorkspace = getWorkspace as ReturnType<typeof vi.fn>
const mockGetActorRole = getActorRole as ReturnType<typeof vi.fn>

const VALID_WS_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const INVALID_WS_ID = 'not-a-uuid'

function renderGuard(wsId: string) {
  return render(
    <MemoryRouter initialEntries={[`/hub/ws/${wsId}/overview`]}>
      <Routes>
        <Route path="/hub/ws/:workspace_id" element={<WorkspaceAccessGuard />}>
          <Route path="overview" element={<div data-testid="workspace-page">Workspace</div>} />
        </Route>
        <Route path="/404" element={<div data-testid="not-found">Not Found</div>} />
        <Route path="/forbidden" element={<div data-testid="forbidden-page">Forbidden</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('WorkspaceAccessGuard (F131 P03)', () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-token')
    mockGetActorRole.mockReturnValue('workspace_user')
    mockGetWorkspace.mockResolvedValue({ data: { workspace_id: VALID_WS_ID } })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // T03-01: Valid workspace ID + member → renders child page
  it('T03-01: renders workspace content for a valid member', async () => {
    renderGuard(VALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-page')).not.toBeNull()
    })
  })

  // T03-02: Non-UUID workspace_id → redirects to /404
  it('T03-02: redirects to /404 for a non-UUID workspace_id', async () => {
    renderGuard(INVALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('not-found')).not.toBeNull()
    })
  })

  // T03-03: 404 from backend → redirects to /404
  it('T03-03: redirects to /404 when workspace is not found (404)', async () => {
    mockGetWorkspace.mockRejectedValueOnce({ response: { status: 404 } })
    renderGuard(VALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('not-found')).not.toBeNull()
    })
  })

  // T03-04: 403 from backend → redirects to /forbidden
  it('T03-04: redirects to /forbidden when user is not a member (403)', async () => {
    mockGetWorkspace.mockRejectedValueOnce({ response: { status: 403 } })
    renderGuard(VALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('forbidden-page')).not.toBeNull()
    })
  })

  // T03-05: Any non-404 error → redirects to /forbidden
  it('T03-05: redirects to /forbidden for unexpected backend errors', async () => {
    mockGetWorkspace.mockRejectedValueOnce({ response: { status: 500 } })
    renderGuard(VALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('forbidden-page')).not.toBeNull()
    })
  })

  // T03-06: platform_admin bypasses the membership check — access is granted
  // even when the workspace fetch fails (cross-tenant access).
  it('T03-06: platform_admin is granted access even when getWorkspace fails', async () => {
    mockGetActorRole.mockReturnValue('platform_admin')
    mockGetWorkspace.mockRejectedValueOnce({ response: { status: 403 } })
    renderGuard(VALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-page')).not.toBeNull()
    })
  })

  // T03-07: Shows loading spinner while the workspace fetch is in progress
  it('T03-07: renders loading spinner while fetching', () => {
    // getWorkspace never resolves in this test
    mockGetWorkspace.mockReturnValue(new Promise(() => {}))
    renderGuard(VALID_WS_ID)
    // Loading spinner uses animate-spin class
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  // T03-08: No token → does not bypass as platform_admin
  it('T03-08: null token results in membership check (non-admin)', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    mockGetActorRole.mockReturnValue(null)
    renderGuard(VALID_WS_ID)
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-page')).not.toBeNull()
    })
    expect(mockGetWorkspace).toHaveBeenCalledWith(VALID_WS_ID)
  })
})
