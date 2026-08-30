/**
 * Unit tests for ExampleSuggestions component
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import ExampleSuggestions from '@/components/nl-rule-builder/ExampleSuggestions'

describe('ExampleSuggestions', () => {
  it('renders heading text', () => {
    render(<ExampleSuggestions onSelect={() => {}} />)
    expect(screen.getByText('Try these examples:')).toBeInTheDocument()
  })

  it('renders all 6 example buttons', () => {
    render(<ExampleSuggestions onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: /Not null check/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Date comparison/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Value in list/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Numeric range/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Reference lookup/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cross-field/i })).toBeInTheDocument()
  })

  it('calls onSelect with correct text when clicking "Not null check"', async () => {
    const onSelect = vi.fn()
    render(<ExampleSuggestions onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Not null check/i }))
    expect(onSelect).toHaveBeenCalledWith('Customer email must not be null')
  })

  it('calls onSelect with correct text when clicking "Date comparison"', async () => {
    const onSelect = vi.fn()
    render(<ExampleSuggestions onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Date comparison/i }))
    expect(onSelect).toHaveBeenCalledWith('Shipping date must be after order date')
  })

  it('calls onSelect with correct text when clicking "Value in list"', async () => {
    const onSelect = vi.fn()
    render(<ExampleSuggestions onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Value in list/i }))
    expect(onSelect).toHaveBeenCalledWith('Status must be one of OPEN, CLOSED, PENDING')
  })

  it('calls onSelect with correct text when clicking "Numeric range"', async () => {
    const onSelect = vi.fn()
    render(<ExampleSuggestions onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: /Numeric range/i }))
    expect(onSelect).toHaveBeenCalledWith('Customer age must be between 18 and 120')
  })

  it('each button has a title attribute with the full rule text', () => {
    render(<ExampleSuggestions onSelect={() => {}} />)
    const btn = screen.getByRole('button', { name: /Not null check/i })
    expect(btn).toHaveAttribute('title', 'Customer email must not be null')
  })
})
