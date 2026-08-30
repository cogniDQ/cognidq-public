/**
 * Unit tests for SignalBreakdownTooltip component
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { SignalBreakdownTooltip } from '@/components/nl-rule-builder/SignalBreakdownTooltip'
import type { SignalBreakdown } from '@/types/resolution'

const breakdown: SignalBreakdown[] = [
  { signal_name: 'lexical_match', score: 0.95, evidence: 'exact match' },
  { signal_name: 'glossary_match', score: 0.8, evidence: 'linked term' },
  { signal_name: 'domain_context', score: 0.0, evidence: 'no match' },
]

describe('SignalBreakdownTooltip', () => {
  it('returns null when no breakdown', () => {
    const { container } = render(<SignalBreakdownTooltip breakdown={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders toggle button when breakdown exists', () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    expect(screen.getByTestId('signal-toggle')).toBeInTheDocument()
    expect(screen.getByText(/Show signal details/i)).toBeInTheDocument()
  })

  it('does not show details initially', () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    expect(screen.queryByTestId('signal-details')).not.toBeInTheDocument()
  })

  it('shows details after clicking toggle', async () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    await userEvent.click(screen.getByTestId('signal-toggle'))
    expect(screen.getByTestId('signal-details')).toBeInTheDocument()
  })

  it('displays signal names when expanded', async () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    await userEvent.click(screen.getByTestId('signal-toggle'))
    expect(screen.getByText('lexical match')).toBeInTheDocument()
    expect(screen.getByText('glossary match')).toBeInTheDocument()
    expect(screen.getByText('domain context')).toBeInTheDocument()
  })

  it('displays signal scores when expanded', async () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    await userEvent.click(screen.getByTestId('signal-toggle'))
    expect(screen.getByText('95%')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('toggles back to hidden', async () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    await userEvent.click(screen.getByTestId('signal-toggle'))
    expect(screen.getByTestId('signal-details')).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('signal-toggle'))
    expect(screen.queryByTestId('signal-details')).not.toBeInTheDocument()
  })

  it('shows "Hide signal details" when expanded', async () => {
    render(<SignalBreakdownTooltip breakdown={breakdown} />)
    await userEvent.click(screen.getByTestId('signal-toggle'))
    expect(screen.getByText(/Hide signal details/i)).toBeInTheDocument()
  })
})
