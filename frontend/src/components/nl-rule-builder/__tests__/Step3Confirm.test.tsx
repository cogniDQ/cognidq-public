/**
 * Unit tests for Step3Confirm component (F127 P03)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import Step3Confirm from '@/components/nl-rule-builder/Step3Confirm'
import { mockParsedResponse } from './testFixtures'

const defaultProps = {
  parseResult: mockParsedResponse,
  draft: { rule_text: 'customer_id must not be null', dataset_id: '', domain: '', severity: 'medium' as const, tags: [], use_context: false },
  onDraftChange: vi.fn(),
  datasets: [{ id: 'ds-1', name: 'Customers', dataset_id: 'ds-1' }],
  onSubmitProposal: vi.fn(),
  isSubmitting: false,
  onBack: vi.fn(),
}

describe('Step3Confirm', () => {
  it('renders step3-confirm container', () => {
    render(<Step3Confirm {...defaultProps} />)
    expect(screen.getByTestId('step3-confirm')).toBeInTheDocument()
  })

  it('renders CompiledConfigPreview with configs', () => {
    render(<Step3Confirm {...defaultProps} />)
    expect(screen.getByTestId('compiled-config-list')).toBeInTheDocument()
  })

  it('submit-proposal-btn is enabled when check_configs exist', () => {
    render(<Step3Confirm {...defaultProps} />)
    expect(screen.getByTestId('submit-proposal-btn')).not.toBeDisabled()
  })

  it('submit-proposal-btn is disabled when check_configs is empty', () => {
    const props = { ...defaultProps, parseResult: { ...mockParsedResponse, check_configs: [] } }
    render(<Step3Confirm {...props} />)
    expect(screen.getByTestId('submit-proposal-btn')).toBeDisabled()
  })

  it('calls onBack when back button clicked', async () => {
    const onBack = vi.fn()
    render(<Step3Confirm {...defaultProps} onBack={onBack} />)
    await userEvent.click(screen.getByTestId('step3-back-btn'))
    expect(onBack).toHaveBeenCalled()
  })

  it('calls onSubmitProposal when submit-proposal-btn clicked', async () => {
    const onSubmitProposal = vi.fn()
    render(<Step3Confirm {...defaultProps} onSubmitProposal={onSubmitProposal} />)
    await userEvent.click(screen.getByTestId('submit-proposal-btn'))
    expect(onSubmitProposal).toHaveBeenCalled()
  })
})
