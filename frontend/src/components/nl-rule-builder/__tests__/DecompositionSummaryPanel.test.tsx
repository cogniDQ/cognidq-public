/**
 * Unit tests for DecompositionSummaryPanel component (F127 P02)
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import DecompositionSummaryPanel from '@/components/nl-rule-builder/DecompositionSummaryPanel'
import { mockDecompositionSummary, mockSingleDecomposition } from './testFixtures'

describe('DecompositionSummaryPanel', () => {
  it('renders obligation count and logic type when count > 1', () => {
    render(<DecompositionSummaryPanel summary={mockDecompositionSummary} />)
    expect(screen.getByTestId('decomposition-summary')).toBeInTheDocument()
    expect(screen.getByText('2 obligations detected')).toBeInTheDocument()
    expect(screen.getByText('AND')).toBeInTheDocument()
  })

  it('renders all obligation subjects', () => {
    render(<DecompositionSummaryPanel summary={mockDecompositionSummary} />)
    expect(screen.getByText('customer_id must not be null')).toBeInTheDocument()
    expect(screen.getByText('email must not be null')).toBeInTheDocument()
  })

  it('is not rendered when count <= 1', () => {
    render(<DecompositionSummaryPanel summary={mockSingleDecomposition} />)
    expect(screen.queryByTestId('decomposition-summary')).not.toBeInTheDocument()
  })
})
