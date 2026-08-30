/**
 * Unit tests for DisambiguationPanel component
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { DisambiguationPanel } from '@/components/nl-rule-builder/DisambiguationPanel'
import type { ResolveResponse } from '@/types/resolution'

const disambigResolution: ResolveResponse = {
  resolved_rule: { rule_type: 'date_comparison' },
  subject_resolution: {
    raw_text: 'shipping date',
    candidates: [
      {
        asset_id: 'asset-1',
        column_name: 'shipping_date',
        dataset_name: 'Orders',
        data_type: 'date',
        overall_score: 0.85,
        confidence_band: 'medium',
        signal_breakdown: [{ signal_name: 'lexical_match', score: 0.95, evidence: 'exact' }],
        evidence_summary: ['lexical_match'],
      },
      {
        asset_id: 'asset-2',
        column_name: 'ship_dt',
        dataset_name: 'Shipments',
        data_type: 'date',
        overall_score: 0.65,
        confidence_band: 'low',
        signal_breakdown: [],
        evidence_summary: [],
      },
    ],
    best_candidate: {
      asset_id: 'asset-1',
      column_name: 'shipping_date',
      dataset_name: 'Orders',
      data_type: 'date',
      overall_score: 0.85,
      confidence_band: 'medium',
      signal_breakdown: [],
      evidence_summary: [],
    },
    requires_disambiguation: true,
  },
  object_resolution: {
    raw_text: 'order date',
    candidates: [
      {
        asset_id: 'asset-3',
        column_name: 'order_date',
        dataset_name: 'Orders',
        data_type: 'date',
        overall_score: 0.95,
        confidence_band: 'high',
        signal_breakdown: [],
        evidence_summary: [],
      },
    ],
    best_candidate: {
      asset_id: 'asset-3',
      column_name: 'order_date',
      dataset_name: 'Orders',
      data_type: 'date',
      overall_score: 0.95,
      confidence_band: 'high',
      signal_breakdown: [],
      evidence_summary: [],
    },
    requires_disambiguation: false,
  },
  overall_confidence: 0.85,
  requires_disambiguation: true,
  resolution_evidence: {},
}

const highConfResolution: ResolveResponse = {
  ...disambigResolution,
  requires_disambiguation: false,
  subject_resolution: {
    ...disambigResolution.subject_resolution,
    requires_disambiguation: false,
  },
}

describe('DisambiguationPanel', () => {
  it('renders panel with data-testid', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByTestId('disambiguation-panel')).toBeInTheDocument()
  })

  it('shows Column Resolution heading', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByText('Column Resolution')).toBeInTheDocument()
  })

  it('shows warning banner when disambiguation required', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByTestId('disambiguation-warning')).toBeInTheDocument()
    expect(screen.getByText('Confirmation required')).toBeInTheDocument()
  })

  it('hides warning banner when disambiguation not required', () => {
    render(
      <DisambiguationPanel
        resolution={highConfResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.queryByTestId('disambiguation-warning')).not.toBeInTheDocument()
  })

  it('shows subject entity section', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByTestId('entity-section-subject')).toBeInTheDocument()
    expect(screen.getByTestId('entity-section-subject')).toHaveTextContent('shipping date')
  })

  it('shows object entity section', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByTestId('entity-section-object')).toBeInTheDocument()
    expect(screen.getByTestId('entity-section-object')).toHaveTextContent('order date')
  })

  it('renders candidate cards for subject', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    // Subject has 2 candidates, object has 1 — both start rank at 1
    const cards = screen.getAllByTestId(/^candidate-card-/)
    expect(cards.length).toBe(3) // 2 subject + 1 object
  })

  it('shows Accept Resolution button', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByTestId('accept-resolution')).toBeInTheDocument()
    expect(screen.getByText('Accept Resolution')).toBeInTheDocument()
  })

  it('shows Cancel button', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    expect(screen.getByTestId('cancel-resolution')).toBeInTheDocument()
  })

  it('calls onCancel when Cancel clicked', async () => {
    const onCancel = vi.fn()
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={onCancel}
      />
    )
    await userEvent.click(screen.getByTestId('cancel-resolution'))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onAccept with selected candidates', async () => {
    const onAccept = vi.fn()
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={onAccept}
        onCancel={() => {}}
      />
    )
    // Default selection is the best_candidate
    await userEvent.click(screen.getByTestId('accept-resolution'))
    expect(onAccept).toHaveBeenCalledWith(
      expect.objectContaining({ subject: 'asset-1' })
    )
  })

  it('updates selection when clicking different candidate', async () => {
    const onAccept = vi.fn()
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={onAccept}
        onCancel={() => {}}
      />
    )
    // Select second candidate
    await userEvent.click(screen.getByTestId('candidate-card-2'))
    await userEvent.click(screen.getByTestId('accept-resolution'))
    expect(onAccept).toHaveBeenCalledWith(
      expect.objectContaining({ subject: 'asset-2' })
    )
  })

  it('shows overall confidence badge', () => {
    render(
      <DisambiguationPanel
        resolution={disambigResolution}
        onAccept={() => {}}
        onCancel={() => {}}
      />
    )
    // 85% appears in both the overall badge and in the subject candidate score
    const badges = screen.getAllByText('85%')
    expect(badges.length).toBeGreaterThanOrEqual(2)
  })
})
