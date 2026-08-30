/**
 * Unit tests for ExplainabilitySection component (F127 P02)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import ExplainabilitySection from '@/components/nl-rule-builder/ExplainabilitySection'
import { mockExplainabilityItems, mockTrustSummary, mockLowTrustSummary } from './testFixtures'

describe('ExplainabilitySection', () => {
  it('renders trust tier badge (high/medium/low)', () => {
    render(<ExplainabilitySection items={mockExplainabilityItems} trustSummary={mockTrustSummary} />)
    expect(screen.getByTestId('trust-tier-badge')).toBeInTheDocument()
    expect(screen.getByTestId('trust-tier-badge').textContent).toContain('High confidence')
  })

  it('renders low trust tier badge', () => {
    render(<ExplainabilitySection items={mockExplainabilityItems} trustSummary={mockLowTrustSummary} />)
    expect(screen.getByTestId('trust-tier-badge').textContent).toContain('Low confidence')
  })

  it('is collapsed by default; expands on toggle click', async () => {
    render(<ExplainabilitySection items={mockExplainabilityItems} trustSummary={mockTrustSummary} />)
    // Collapsed by default — body not visible
    expect(screen.queryByTestId('explainability-body')).not.toBeInTheDocument()
    // Expand
    await userEvent.click(screen.getByTestId('explainability-toggle'))
    expect(screen.getByTestId('explainability-body')).toBeInTheDocument()
  })

  it('renders signal entries when expanded', async () => {
    render(<ExplainabilitySection items={mockExplainabilityItems} trustSummary={mockTrustSummary} />)
    await userEvent.click(screen.getByTestId('explainability-toggle'))
    expect(screen.getByTestId('signal-entry-rule_type-0')).toBeInTheDocument()
    expect(screen.getByTestId('signal-entry-subject-0')).toBeInTheDocument()
  })

  it('renders caveats when trust_summary.caveats is non-empty', () => {
    // Low confidence summaries default to expanded to surface the "why".
    render(<ExplainabilitySection items={mockExplainabilityItems} trustSummary={mockLowTrustSummary} />)
    expect(screen.getByTestId('caveats-list')).toBeInTheDocument()
    expect(screen.getByText('Subject ambiguous')).toBeInTheDocument()
  })

  it('is not rendered when there are no items and no trust summary', () => {
    render(<ExplainabilitySection items={[]} trustSummary={null} />)
    expect(screen.queryByTestId('explainability-section')).not.toBeInTheDocument()
  })
})
