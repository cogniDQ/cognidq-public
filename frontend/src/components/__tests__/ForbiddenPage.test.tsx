/**
 * ForbiddenPage — unit tests — F129 P05
 *
 * Test coverage:
 *   1. Renders "Access Denied" heading
 *   2. "Go Back" button calls navigate(-1)
 *   3. "Go to DQ Hub" button navigates to /hub
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import ForbiddenPage from '@/pages/admin/ForbiddenPage'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('ForbiddenPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
  })

  function renderPage() {
    return render(
      <MemoryRouter>
        <ForbiddenPage />
      </MemoryRouter>,
    )
  }

  it('renders Access Denied heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: /access denied/i })).toBeInTheDocument()
  })

  it('"Go Back" button calls navigate(-1)', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /go back/i }))
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })

  it('"Go to DQ Hub" button navigates to /hub', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /go to dq hub/i }))
    expect(mockNavigate).toHaveBeenCalledWith('/hub')
  })
})
