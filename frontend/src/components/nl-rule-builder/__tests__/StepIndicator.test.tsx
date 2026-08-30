/**
 * Unit tests for StepIndicator component (F127 P01)
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import StepIndicator from '@/components/nl-rule-builder/StepIndicator'

describe('StepIndicator', () => {
  it('renders all three step labels: Input, Review, Confirm', () => {
    render(<StepIndicator currentStep={1} />)
    expect(screen.getByText('Input')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Confirm')).toBeInTheDocument()
  })

  it('marks the active step with aria-current="step"', () => {
    render(<StepIndicator currentStep={2} />)
    const active = screen.getByTestId('step-bubble-2')
    expect(active).toHaveAttribute('aria-current', 'step')
    expect(screen.getByTestId('step-bubble-1')).not.toHaveAttribute('aria-current')
    expect(screen.getByTestId('step-bubble-3')).not.toHaveAttribute('aria-current')
  })

  it('renders a check icon for completed steps', () => {
    render(<StepIndicator currentStep={3} />)
    // Steps 1 and 2 should be completed — they should NOT show step numbers
    // Step 3 is active — shows number 3
    // We can verify by checking that step numbers 1 and 2 are not visible as text in bubbles
    // The check icon doesn't carry text, so the number text is absent for completed steps
    const bubble1 = screen.getByTestId('step-bubble-1')
    const bubble2 = screen.getByTestId('step-bubble-2')
    const bubble3 = screen.getByTestId('step-bubble-3')
    // completed bubbles contain a svg (Check icon), not a text node with the step number
    expect(bubble1.textContent).toBe('')
    expect(bubble2.textContent).toBe('')
    // active bubble shows step number
    expect(bubble3.textContent).toBe('3')
  })
})
