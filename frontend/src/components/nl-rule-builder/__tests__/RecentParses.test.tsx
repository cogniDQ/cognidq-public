/**
 * Unit tests for RecentParses component
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import RecentParses from '@/components/nl-rule-builder/RecentParses'
import type { RecentParseEntry } from '@/types/nlRuleBuilder'

const entries: RecentParseEntry[] = [
  {
    rule_text: 'email must not be null',
    confidence: 0.95,
    rule_type: 'not_null',
    timestamp: '2024-01-15T10:30:00Z',
  },
  {
    rule_text: 'age must be between 18 and 120',
    confidence: 0.78,
    rule_type: 'numeric_range',
    timestamp: '2024-01-15T10:25:00Z',
  },
]

describe('RecentParses', () => {
  it('returns null when no entries', () => {
    const { container } = render(<RecentParses entries={[]} onRestore={() => {}} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders heading when entries exist', () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    expect(screen.getByText('Recent Parses')).toBeInTheDocument()
  })

  it('shows entry count', () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows rule text for each entry', () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    expect(screen.getByText('email must not be null')).toBeInTheDocument()
    expect(screen.getByText('age must be between 18 and 120')).toBeInTheDocument()
  })

  it('shows confidence as percentage', () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    expect(screen.getByText('95%')).toBeInTheDocument()
    expect(screen.getByText('78%')).toBeInTheDocument()
  })

  it('shows rule type', () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    expect(screen.getByText('not null')).toBeInTheDocument()
    expect(screen.getByText('numeric range')).toBeInTheDocument()
  })

  it('calls onRestore when clicking an entry', async () => {
    const onRestore = vi.fn()
    render(<RecentParses entries={entries} onRestore={onRestore} />)
    await userEvent.click(screen.getByText('email must not be null'))
    expect(onRestore).toHaveBeenCalledWith('email must not be null')
  })

  it('collapses on toggle click', async () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    expect(screen.getByText('email must not be null')).toBeInTheDocument()

    // Click the toggle button (the heading area)
    await userEvent.click(screen.getByText('Recent Parses'))
    expect(screen.queryByText('email must not be null')).not.toBeInTheDocument()
  })

  it('expands again after collapse', async () => {
    render(<RecentParses entries={entries} onRestore={() => {}} />)
    await userEvent.click(screen.getByText('Recent Parses'))
    expect(screen.queryByText('email must not be null')).not.toBeInTheDocument()
    await userEvent.click(screen.getByText('Recent Parses'))
    expect(screen.getByText('email must not be null')).toBeInTheDocument()
  })
})
