/**
 * Unit tests for Step2Review component (F127 P02)
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import Step2Review from '@/components/nl-rule-builder/Step2Review'
import {
  mockParsedResponse,
  mockClarificationResponse,
  mockCompoundParsedResponse,
} from './testFixtures'

const defaultProps = {
  resolution: null,
  onClarify: vi.fn(),
  isClarifying: false,
  onAcceptResolution: vi.fn(),
  onCancelResolution: vi.fn(),
  isResolving: false,
  onContinue: vi.fn(),
  onBack: vi.fn(),
}

describe('Step2Review', () => {
  it('renders parse result panel for a successfully parsed rule', () => {
    render(<Step2Review {...defaultProps} parseResult={mockParsedResponse} />)
    expect(screen.getByTestId('step2-review')).toBeInTheDocument()
  })

  it('shows "Continue to Confirm" button when status is parsed and no blockers', () => {
    render(<Step2Review {...defaultProps} parseResult={mockParsedResponse} />)
    expect(screen.getByTestId('step2-continue-btn')).toBeInTheDocument()
  })

  it('hides "Continue to Confirm" when status is needs_clarification', () => {
    render(<Step2Review {...defaultProps} parseResult={mockClarificationResponse} />)
    expect(screen.queryByTestId('step2-continue-btn')).not.toBeInTheDocument()
  })

  it('shows ClarificationPanel inline when needs_clarification', () => {
    render(<Step2Review {...defaultProps} parseResult={mockClarificationResponse} />)
    expect(screen.getByTestId('clarification-panel')).toBeInTheDocument()
  })

  it('shows DecompositionSummaryPanel when decomposition count > 1', () => {
    render(<Step2Review {...defaultProps} parseResult={mockCompoundParsedResponse} />)
    expect(screen.getByTestId('decomposition-summary')).toBeInTheDocument()
  })
})
