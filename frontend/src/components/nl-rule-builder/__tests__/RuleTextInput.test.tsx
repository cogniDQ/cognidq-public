/**
 * Unit tests for RuleTextInput component
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import RuleTextInput from '@/components/nl-rule-builder/RuleTextInput'

describe('RuleTextInput', () => {
  it('renders textarea with label', () => {
    render(<RuleTextInput value="" onChange={() => {}} maxLength={500} />)
    expect(screen.getByLabelText('Business Rule')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('displays current value', () => {
    render(<RuleTextInput value="email must not be null" onChange={() => {}} maxLength={500} />)
    expect(screen.getByRole('textbox')).toHaveValue('email must not be null')
  })

  it('shows character count', () => {
    render(<RuleTextInput value="hello" onChange={() => {}} maxLength={500} />)
    expect(screen.getByText('5/500')).toBeInTheDocument()
  })

  it('shows 0/500 when empty', () => {
    render(<RuleTextInput value="" onChange={() => {}} maxLength={500} />)
    expect(screen.getByText('0/500')).toBeInTheDocument()
  })

  it('calls onChange when typing', async () => {
    const onChange = vi.fn()
    render(<RuleTextInput value="" onChange={onChange} maxLength={500} />)
    const textarea = screen.getByRole('textbox')
    await userEvent.type(textarea, 'a')
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it('has correct maxLength attribute', () => {
    render(<RuleTextInput value="" onChange={() => {}} maxLength={300} />)
    expect(screen.getByRole('textbox')).toHaveAttribute('maxLength', '300')
  })

  it('shows placeholder text', () => {
    render(<RuleTextInput value="" onChange={() => {}} maxLength={500} />)
    expect(screen.getByPlaceholderText(/shipping date/i)).toBeInTheDocument()
  })

  it('has correct id for label association', () => {
    render(<RuleTextInput value="" onChange={() => {}} maxLength={500} />)
    expect(screen.getByRole('textbox')).toHaveAttribute('id', 'rule-text')
  })
})
