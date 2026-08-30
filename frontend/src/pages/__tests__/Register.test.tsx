/**
 * Register.tsx — unit tests — F131 P01 (BUG-019)
 *
 * Verifies that 422 Pydantic validation errors are displayed as a
 * human-readable string instead of crashing the form.
 *
 * Test IDs: T01-01 through T01-04
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import Register from '@/pages/auth/Register'

// ── Mock AuthContext ──────────────────────────────────────────────────────────
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '@/contexts/AuthContext'
const mockUseAuth = useAuth as ReturnType<typeof vi.fn>

function renderRegister() {
  return render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>,
  )
}

function fillAndSubmit(emailVal = 'test@example.com', passwordVal = 'ValidPass1') {
  const emailInput = screen.getByPlaceholderText(/you@example.com/i)
  const passwordInputs = screen.getAllByPlaceholderText(/\u2022/)
  fireEvent.change(emailInput, { target: { name: 'email', value: emailVal } })
  fireEvent.change(passwordInputs[0], { target: { name: 'password', value: passwordVal } })
  if (passwordInputs.length > 1) {
    fireEvent.change(passwordInputs[1], { target: { name: 'confirmPassword', value: passwordVal } })
  }
  fireEvent.submit(screen.getByRole('button', { name: /create account/i }))
}

describe('Register — 422 error handling (F131 P01)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  // T01-01: Array of Pydantic errors is joined into a readable string
  it('T01-01: displays Pydantic array detail as joined string', async () => {
    const mockRegister = vi.fn().mockRejectedValueOnce({
      response: {
        data: {
          detail: [
            { msg: 'value is not a valid email address', loc: ['body', 'email'] },
            { msg: 'field required', loc: ['body', 'password'] },
          ],
        },
      },
    })
    mockUseAuth.mockReturnValue({ register: mockRegister })
    renderRegister()
    fillAndSubmit('bademail')

    await waitFor(() => {
      expect(screen.queryByText(/value is not a valid email address/i)).not.toBeNull()
    })
  })

  // T01-02: Plain string detail is shown as-is
  it('T01-02: displays plain string detail directly', async () => {
    const mockRegister = vi.fn().mockRejectedValueOnce({
      response: { data: { detail: 'Email already registered' } },
    })
    mockUseAuth.mockReturnValue({ register: mockRegister })
    renderRegister()
    fillAndSubmit()

    await waitFor(() => {
      expect(screen.queryByText(/Email already registered/i)).not.toBeNull()
    })
  })

  // T01-03: Missing response detail falls back to generic message
  it('T01-03: falls back to generic message when detail is absent', async () => {
    const mockRegister = vi.fn().mockRejectedValueOnce(new Error('Network Error'))
    mockUseAuth.mockReturnValue({ register: mockRegister })
    renderRegister()
    fillAndSubmit()

    await waitFor(() => {
      expect(screen.queryByText(/Registration failed. Please try again./i)).not.toBeNull()
    })
  })

  // T01-04: Form inputs remain enabled after a 422 error
  it('T01-04: form inputs stay enabled after 422 error', async () => {
    const mockRegister = vi.fn().mockRejectedValueOnce({
      response: {
        data: { detail: [{ msg: 'invalid email', loc: ['body', 'email'] }] },
      },
    })
    mockUseAuth.mockReturnValue({ register: mockRegister })
    renderRegister()
    const emailInput = screen.getByPlaceholderText(/you@example.com/i)
    fillAndSubmit('bad')

    await waitFor(() => {
      expect(screen.queryByText(/invalid email/i)).not.toBeNull()
    })
    expect(emailInput).not.toBeDisabled()
  })
})
