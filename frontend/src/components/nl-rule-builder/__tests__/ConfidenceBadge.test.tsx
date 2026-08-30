/**
 * Unit tests for ConfidenceBadge component
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ConfidenceBadge from '@/components/nl-rule-builder/ConfidenceBadge'

describe('ConfidenceBadge', () => {
  it('shows percentage', () => {
    render(<ConfidenceBadge confidence={0.95} />)
    expect(screen.getByText('95%')).toBeInTheDocument()
  })

  it('shows "High" for >= 0.9', () => {
    render(<ConfidenceBadge confidence={0.92} />)
    expect(screen.getByText('High')).toBeInTheDocument()
    expect(screen.getByText('92%')).toBeInTheDocument()
  })

  it('shows "Medium" for >= 0.7 and < 0.9', () => {
    render(<ConfidenceBadge confidence={0.75} />)
    expect(screen.getByText('Medium')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('shows "Low" for < 0.7', () => {
    render(<ConfidenceBadge confidence={0.45} />)
    expect(screen.getByText('Low')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('rounds percentage', () => {
    render(<ConfidenceBadge confidence={0.876} />)
    expect(screen.getByText('88%')).toBeInTheDocument()
  })

  it('handles 1.0 confidence', () => {
    render(<ConfidenceBadge confidence={1.0} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('handles 0.0 confidence', () => {
    render(<ConfidenceBadge confidence={0.0} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
    expect(screen.getByText('Low')).toBeInTheDocument()
  })

  it('shows green bar for high confidence', () => {
    const { container } = render(<ConfidenceBadge confidence={0.95} />)
    const bar = container.querySelector('.bg-green-500')
    expect(bar).toBeInTheDocument()
  })

  it('shows yellow bar for medium confidence', () => {
    const { container } = render(<ConfidenceBadge confidence={0.75} />)
    const bar = container.querySelector('.bg-yellow-500')
    expect(bar).toBeInTheDocument()
  })

  it('shows red bar for low confidence', () => {
    const { container } = render(<ConfidenceBadge confidence={0.3} />)
    const bar = container.querySelector('.bg-red-500')
    expect(bar).toBeInTheDocument()
  })
})
