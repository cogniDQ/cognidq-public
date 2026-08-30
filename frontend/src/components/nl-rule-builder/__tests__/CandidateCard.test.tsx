/**
 * Unit tests for CandidateCard component
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { CandidateCard } from '@/components/nl-rule-builder/CandidateCard'
import type { ResolutionCandidate } from '@/types/resolution'

const candidate: ResolutionCandidate = {
  asset_id: 'asset-1',
  column_name: 'shipping_date',
  dataset_name: 'Orders Curated',
  data_type: 'date',
  overall_score: 0.85,
  confidence_band: 'medium',
  signal_breakdown: [
    { signal_name: 'lexical_match', score: 0.95, evidence: 'normalized match' },
  ],
  evidence_summary: ['lexical_match'],
}

describe('CandidateCard', () => {
  it('renders column name', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />)
    expect(screen.getByTestId('candidate-name')).toHaveTextContent('shipping_date')
  })

  it('renders dataset name', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />)
    expect(screen.getByText(/Orders Curated/)).toBeInTheDocument()
  })

  it('renders rank number', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={2} onSelect={() => {}} />)
    expect(screen.getByText('#2')).toBeInTheDocument()
  })

  it('renders data type', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />)
    expect(screen.getByText(/Type: date/)).toBeInTheDocument()
  })

  it('renders score as percentage', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />)
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  it('renders evidence summary tags', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />)
    expect(screen.getByText('lexical match')).toBeInTheDocument()
  })

  it('shows check icon when selected', () => {
    const { container } = render(
      <CandidateCard candidate={candidate} isSelected={true} rank={1} onSelect={() => {}} />
    )
    // Selected state has ring-1 class
    const card = container.querySelector('[data-testid="candidate-card-1"]')
    expect(card).toHaveClass('ring-1')
  })

  it('does not have ring when not selected', () => {
    const { container } = render(
      <CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />
    )
    const card = container.querySelector('[data-testid="candidate-card-1"]')
    expect(card).not.toHaveClass('ring-1')
  })

  it('calls onSelect when clicked', async () => {
    const onSelect = vi.fn()
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={onSelect} />)
    await userEvent.click(screen.getByTestId('candidate-card-1'))
    expect(onSelect).toHaveBeenCalledWith(candidate)
  })

  it('has correct data-testid', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={3} onSelect={() => {}} />)
    expect(screen.getByTestId('candidate-card-3')).toBeInTheDocument()
  })

  it('handles high confidence band colors', () => {
    const highCandidate = { ...candidate, confidence_band: 'high' as const, overall_score: 0.95 }
    const { container } = render(
      <CandidateCard candidate={highCandidate} isSelected={false} rank={1} onSelect={() => {}} />
    )
    expect(container.querySelector('.bg-green-100')).toBeInTheDocument()
  })

  it('handles low confidence band colors', () => {
    const lowCandidate = { ...candidate, confidence_band: 'low' as const, overall_score: 0.3 }
    const { container } = render(
      <CandidateCard candidate={lowCandidate} isSelected={false} rank={1} onSelect={() => {}} />
    )
    expect(container.querySelector('.bg-red-100')).toBeInTheDocument()
  })

  it('renders signal breakdown toggle', () => {
    render(<CandidateCard candidate={candidate} isSelected={false} rank={1} onSelect={() => {}} />)
    expect(screen.getByTestId('signal-toggle')).toBeInTheDocument()
  })
})
