/**
 * Unit tests for WarningsBanner component (F127 P02)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import WarningsBanner from '@/components/nl-rule-builder/WarningsBanner'

describe('WarningsBanner', () => {
  it('renders warnings list when warnings are provided', () => {
    render(<WarningsBanner warnings={['Subject ambiguous', 'No glossary match']} />)
    expect(screen.getByTestId('warnings-banner')).toBeInTheDocument()
    expect(screen.getByTestId('warnings-list')).toBeInTheDocument()
    expect(screen.getByText('Subject ambiguous')).toBeInTheDocument()
    expect(screen.getByText('No glossary match')).toBeInTheDocument()
  })

  it('toggles warnings list visibility on collapse/expand button click', async () => {
    render(<WarningsBanner warnings={['Warning 1']} />)
    // Initially expanded
    expect(screen.getByTestId('warnings-list')).toBeInTheDocument()
    // Collapse
    const toggle = screen.getByRole('button')
    await userEvent.click(toggle)
    expect(screen.queryByTestId('warnings-list')).not.toBeInTheDocument()
    // Expand again
    await userEvent.click(toggle)
    expect(screen.getByTestId('warnings-list')).toBeInTheDocument()
  })

  it('is not rendered when warnings array is empty', () => {
    render(<WarningsBanner warnings={[]} />)
    expect(screen.queryByTestId('warnings-banner')).not.toBeInTheDocument()
  })
})
