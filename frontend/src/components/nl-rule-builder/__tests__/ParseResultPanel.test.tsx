/**
 * Unit tests for ParseResultPanel component
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ParseResultPanel from '@/components/nl-rule-builder/ParseResultPanel'
import type { ParseRuleResponse } from '@/types/nlRuleBuilder'

const mockResult: ParseRuleResponse = {
  request_id: 'req-1',
  parsed_rule: {
    schema_version: '1.0',
    rule_type: 'not_null',
    subject: { raw_text: 'customer email' },
    operator: 'is_not_null',
    conditions: [],
    constraints: [],
    confidence: 0.95,
    requires_disambiguation: false,
    parse_warnings: [],
  },
  status: 'parsed',
  suggestions: [],
}

describe('ParseResultPanel', () => {
  it('shows placeholder when no result', () => {
    render(<ParseResultPanel result={null} isPending={false} error={null} />)
    expect(screen.getByText(/Enter a business rule/i)).toBeInTheDocument()
  })

  it('shows loading spinner when pending', () => {
    render(<ParseResultPanel result={null} isPending={true} error={null} />)
    expect(screen.getByText(/Interpreting your rule/i)).toBeInTheDocument()
  })

  it('shows error message', () => {
    const error = new Error('Parser failed')
    render(<ParseResultPanel result={null} isPending={false} error={error} />)
    expect(screen.getByText('Parse Error')).toBeInTheDocument()
    expect(screen.getByText('Parser failed')).toBeInTheDocument()
  })

  it('shows parse result heading', () => {
    render(<ParseResultPanel result={mockResult} isPending={false} error={null} />)
    expect(screen.getByText('Rule Parsed')).toBeInTheDocument()
  })

  it('shows confidence percentage', () => {
    render(<ParseResultPanel result={mockResult} isPending={false} error={null} />)
    expect(screen.getByText('95%')).toBeInTheDocument()
  })

  it('shows rule type', () => {
    render(<ParseResultPanel result={mockResult} isPending={false} error={null} />)
    expect(screen.getByText('not null')).toBeInTheDocument()
  })

  it('shows quick stat labels', () => {
    render(<ParseResultPanel result={mockResult} isPending={false} error={null} />)
    expect(screen.getByText('Rule Type')).toBeInTheDocument()
    expect(screen.getByText('Datasets')).toBeInTheDocument()
    expect(screen.getByText('Columns')).toBeInTheDocument()
    expect(screen.getByText('Checks')).toBeInTheDocument()
  })

  it('shows detected dataset, column, and check counts', () => {
    const result: ParseRuleResponse = {
      ...mockResult,
      detected_datasets: [
        { dataset_name: 'customers', match_score: 0.9, match_reason: 'name match' },
      ],
      detected_columns: [
        { raw_text: 'email', role: 'subject' },
        { raw_text: 'name', role: 'object' },
      ],
      check_configs: [
        {
          check_dimension: 'completeness',
          check_subtype: 'not_null',
          columns: ['email'],
          config: {},
          thresholds: {} as never,
          severity: 'high',
          rule_name: 'email not null',
        },
      ],
    }
    render(<ParseResultPanel result={result} isPending={false} error={null} />)
    expect(screen.getByText('1 matched')).toBeInTheDocument()
    expect(screen.getByText('2 detected')).toBeInTheDocument()
    expect(screen.getByText('1 configured')).toBeInTheDocument()
  })

  it('shows column comparison rule type', () => {
    const result: ParseRuleResponse = {
      ...mockResult,
      parsed_rule: {
        ...mockResult.parsed_rule!,
        rule_type: 'column_comparison',
        object: { raw_text: 'order date' },
        conditions: [{ field: { raw_text: 'ship_date' }, operator: 'greater_than' }],
      },
    }
    render(<ParseResultPanel result={result} isPending={false} error={null} />)
    expect(screen.getByText('column comparison')).toBeInTheDocument()
  })

  it('shows "High" badge for high confidence', () => {
    render(<ParseResultPanel result={mockResult} isPending={false} error={null} />)
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('shows "Low" badge for low confidence', () => {
    const result: ParseRuleResponse = {
      ...mockResult,
      parsed_rule: { ...mockResult.parsed_rule!, confidence: 0.4 },
    }
    render(<ParseResultPanel result={result} isPending={false} error={null} />)
    expect(screen.getByText('Low')).toBeInTheDocument()
  })

  it('shows cannot_interpret status', () => {
    const result: ParseRuleResponse = {
      request_id: 'req-2',
      parsed_rule: null,
      status: 'cannot_interpret',
      reason: 'No actionable rule detected',
      suggestions: ['Try specifying a column'],
    }
    render(<ParseResultPanel result={result} isPending={false} error={null} />)
    expect(screen.getByText('Could Not Interpret')).toBeInTheDocument()
    expect(screen.getByText('No actionable rule detected')).toBeInTheDocument()
  })
})
