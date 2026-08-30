/**
 * Unit tests for ClarificationPanel component (F127 P02)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import ClarificationPanel from '@/components/nl-rule-builder/ClarificationPanel'
import { mockClarifyingQuestions } from './testFixtures'

describe('ClarificationPanel', () => {
  it('renders all clarifying questions', () => {
    render(
      <ClarificationPanel
        questions={mockClarifyingQuestions}
        context="Could not determine target dataset."
        onSubmit={vi.fn()}
        isSubmitting={false}
      />
    )
    expect(screen.getByTestId('clarification-panel')).toBeInTheDocument()
    expect(screen.getByText('Which dataset does this rule apply to?')).toBeInTheDocument()
  })

  it('shows context string when context provided', () => {
    render(
      <ClarificationPanel
        questions={mockClarifyingQuestions}
        context="Could not determine target dataset."
        onSubmit={vi.fn()}
        isSubmitting={false}
      />
    )
    expect(screen.getByTestId('clarification-context')).toBeInTheDocument()
    expect(screen.getByText('Could not determine target dataset.')).toBeInTheDocument()
  })

  it('"Submit Answers" is disabled when required question has no answer', () => {
    render(
      <ClarificationPanel
        questions={mockClarifyingQuestions}
        onSubmit={vi.fn()}
        isSubmitting={false}
      />
    )
    expect(screen.getByTestId('submit-answers-btn')).toBeDisabled()
  })

  it('calls onSubmit with answers when an option is selected and submitted', async () => {
    const onSubmit = vi.fn()
    render(
      <ClarificationPanel
        questions={mockClarifyingQuestions}
        onSubmit={onSubmit}
        isSubmitting={false}
      />
    )
    // Select an option chip
    await userEvent.click(screen.getByText('customers'))
    // Submit button should now be enabled
    expect(screen.getByTestId('submit-answers-btn')).not.toBeDisabled()
    await userEvent.click(screen.getByTestId('submit-answers-btn'))
    expect(onSubmit).toHaveBeenCalledWith({ dataset: 'customers' })
  })
})
