/**
 * Unit tests for Step1Input component (F127 P01)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import Step1Input from '@/components/nl-rule-builder/Step1Input'
import type { NLRuleDraft } from '@/types/nlRuleBuilder'

const defaultDraft: NLRuleDraft = {
  rule_text: '',
  dataset_id: '',
  domain: '',
  severity: 'medium',
  tags: [],
  use_context: false,
}

const defaultProps = {
  draft: defaultDraft,
  onDraftChange: vi.fn(),
  onParse: vi.fn(),
  isParseLoading: false,
  parseError: null,
  datasets: [],
  history: [],
  savedParses: undefined,
}

describe('Step1Input', () => {
  it('renders RuleTextInput, ContextPanel, and ExampleSuggestions', () => {
    render(<Step1Input {...defaultProps} />)
    // RuleTextInput renders a textarea with id "rule-text"
    expect(screen.getByLabelText(/business rule/i)).toBeInTheDocument()
    // ContextPanel renders dataset selector
    expect(screen.getByLabelText('Dataset')).toBeInTheDocument()
    // ExampleSuggestions renders example chips
    expect(screen.getByText('Try these examples:')).toBeInTheDocument()
  })

  it('"Interpret Rule" button is disabled when rule text is empty', () => {
    render(<Step1Input {...defaultProps} draft={{ ...defaultDraft, rule_text: '' }} />)
    expect(screen.getByTestId('interpret-btn')).toBeDisabled()
  })

  it('"Interpret Rule" button is enabled when rule text and dataset are set', () => {
    render(<Step1Input {...defaultProps} draft={{ ...defaultDraft, rule_text: 'customer_id must not be null', dataset_id: 'ds-1' }} />)
    expect(screen.getByTestId('interpret-btn')).not.toBeDisabled()
  })

  it('calls onParse when Interpret Rule button is clicked', async () => {
    const onParse = vi.fn()
    render(
      <Step1Input
        {...defaultProps}
        onParse={onParse}
        draft={{ ...defaultDraft, rule_text: 'customer_id must not be null', dataset_id: 'ds-1' }}
      />
    )
    await userEvent.click(screen.getByTestId('interpret-btn'))
    expect(onParse).toHaveBeenCalledOnce()
  })

  it('shows inline error banner when parseError prop is set', () => {
    render(
      <Step1Input
        {...defaultProps}
        parseError={new Error('Parse service unavailable')}
      />
    )
    expect(screen.getByTestId('parse-error-banner')).toBeInTheDocument()
    expect(screen.getByText('Parse service unavailable')).toBeInTheDocument()
  })

  it('does not show error banner when parseError is null', () => {
    render(<Step1Input {...defaultProps} parseError={null} />)
    expect(screen.queryByTestId('parse-error-banner')).not.toBeInTheDocument()
  })

  it('"Interpret Rule" button is disabled when isParseLoading is true', () => {
    render(
      <Step1Input
        {...defaultProps}
        draft={{ ...defaultDraft, rule_text: 'some rule' }}
        isParseLoading
      />
    )
    expect(screen.getByTestId('interpret-btn')).toBeDisabled()
  })
})
