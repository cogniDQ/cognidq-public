/**
 * Unit tests for ContextPanel component  
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import ContextPanel from '@/components/nl-rule-builder/ContextPanel'
import type { NLRuleDraft } from '@/types/nlRuleBuilder'

const defaultDraft: NLRuleDraft = {
  rule_text: '',
  dataset_id: '',
  domain: '',
  severity: 'medium',
  tags: [],
  use_context: false,
}

const datasets = [
  { id: 'ds-1', name: 'Customers' },
  { id: 'ds-2', name: 'Orders' },
]

describe('ContextPanel', () => {
  it('renders heading', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={[]} />)
    expect(screen.getByText('Context (optional)')).toBeInTheDocument()
  })

  it('renders dataset selector with default option', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={datasets} />)
    const select = screen.getByLabelText('Dataset')
    expect(select).toBeInTheDocument()
    expect(screen.getByText('— Select dataset —')).toBeInTheDocument()
  })

  it('renders dataset options', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={datasets} />)
    expect(screen.getByText('Customers')).toBeInTheDocument()
    expect(screen.getByText('Orders')).toBeInTheDocument()
  })

  it('calls onChange when dataset selected', async () => {
    const onChange = vi.fn()
    render(<ContextPanel draft={defaultDraft} onChange={onChange} datasets={datasets} />)
    await userEvent.selectOptions(screen.getByLabelText('Dataset'), 'ds-1')
    expect(onChange).toHaveBeenCalledWith({ dataset_id: 'ds-1' })
  })

  it('renders domain input', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={[]} />)
    expect(screen.getByLabelText('Business Domain')).toBeInTheDocument()
  })

  it('calls onChange when domain typed', async () => {
    const onChange = vi.fn()
    render(<ContextPanel draft={defaultDraft} onChange={onChange} datasets={[]} />)
    await userEvent.type(screen.getByLabelText('Business Domain'), 'F')
    expect(onChange).toHaveBeenCalledWith({ domain: 'F' })
  })

  it('renders severity selector with 5 options', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={[]} />)
    const select = screen.getByLabelText('Severity')
    expect(select).toBeInTheDocument()
    expect(select).toHaveValue('medium')
  })

  it('calls onChange when severity changed', async () => {
    const onChange = vi.fn()
    render(<ContextPanel draft={defaultDraft} onChange={onChange} datasets={[]} />)
    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'critical')
    expect(onChange).toHaveBeenCalledWith({ severity: 'critical' })
  })

  it('renders use context checkbox', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={[]} />)
    expect(screen.getByLabelText(/Use column context/i)).toBeInTheDocument()
  })

  it('renders tags label', () => {
    render(<ContextPanel draft={defaultDraft} onChange={() => {}} datasets={[]} />)
    expect(screen.getByText('Tags')).toBeInTheDocument()
  })

  it('reflects selected dataset in value', () => {
    const draft = { ...defaultDraft, dataset_id: 'ds-2' }
    render(<ContextPanel draft={draft} onChange={() => {}} datasets={datasets} />)
    expect(screen.getByLabelText('Dataset')).toHaveValue('ds-2')
  })

  it('reflects severity in value', () => {
    const draft = { ...defaultDraft, severity: 'high' as const }
    render(<ContextPanel draft={draft} onChange={() => {}} datasets={[]} />)
    expect(screen.getByLabelText('Severity')).toHaveValue('high')
  })
})
