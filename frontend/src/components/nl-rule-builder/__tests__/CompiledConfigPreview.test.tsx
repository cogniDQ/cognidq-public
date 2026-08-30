/**
 * Unit tests for CompiledConfigPreview component (F127 P03)
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import CompiledConfigPreview from '@/components/nl-rule-builder/CompiledConfigPreview'
import { mockCheckConfigs } from './testFixtures'

describe('CompiledConfigPreview', () => {
  it('renders one card per check config', () => {
    render(<CompiledConfigPreview configs={mockCheckConfigs} />)
    expect(screen.getByTestId('compiled-config-list')).toBeInTheDocument()
    expect(screen.getByTestId('config-card-0')).toBeInTheDocument()
  })

  it('shows rule_name and severity badge per card', () => {
    render(<CompiledConfigPreview configs={mockCheckConfigs} />)
    expect(screen.getByText('customer_id must not be null')).toBeInTheDocument()
    expect(screen.getAllByText('high').length).toBeGreaterThan(0)
  })

  it('shows empty-configs warning when array is empty', () => {
    render(<CompiledConfigPreview configs={[]} />)
    expect(screen.getByTestId('compiled-config-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('compiled-config-list')).not.toBeInTheDocument()
  })
})
