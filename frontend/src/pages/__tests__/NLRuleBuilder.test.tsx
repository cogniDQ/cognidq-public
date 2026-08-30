/**
 * Unit tests for NLRuleBuilder page — F127 P01 (step shell + Step 1 integration)
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import NLRuleBuilder from '@/pages/NLRuleBuilder'

// Mock services
vi.mock('@/services/nlRuleBuilderService', () => ({
  parseRule: vi.fn(),
  resolveRule: vi.fn(),
  listParses: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createFlowFromParse: vi.fn(),
}))

vi.mock('@/services/proposalService', () => ({
  createProposal: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: { items: [] } }),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}))

// useTenantScopedPath (used by the page) calls useWorkspace(), which throws
// without a provider. Mock the context to supply the workspace value shape.
vi.mock('@/contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    currentWorkspace: 'ws-test',
    workspaces: [],
    switchWorkspace: vi.fn(),
    loading: false,
    currentWorkspaceDetail: null,
    setCurrentWorkspaceDetail: vi.fn(),
    currentTenantId: 'tenant-1',
  }),
  WorkspaceProvider: ({ children }: { children: React.ReactNode }) => children,
}))

function renderPage() {
  // Spec §4.3 — a dataset is mandatory before parsing. Pre-seed the saved
  // draft so the "Interpret Rule" button can be enabled once rule text is
  // entered (mirrors a user having already picked a dataset).
  localStorage.setItem(
    'nl-rule-draft-ws-test',
    JSON.stringify({
      rule_text: '',
      dataset_id: 'ds-1',
      domain: '',
      severity: 'medium',
      tags: [],
      use_context: true,
    }),
  )
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/hub/ws/ws-test/rule-builder']}>
        <Routes>
          <Route path="/hub/ws/:workspace_id/rule-builder" element={<NLRuleBuilder />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('NLRuleBuilder page (F127 shell)', () => {
  it('renders StepIndicator with all three step labels on mount', () => {
    renderPage()
    expect(screen.getByText('Input')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Confirm')).toBeInTheDocument()
  })

  it('shows Step 1 content (rule text area) on initial load', () => {
    renderPage()
    expect(screen.getByLabelText(/business rule/i)).toBeInTheDocument()
    expect(screen.getByTestId('interpret-btn')).toBeInTheDocument()
  })

  it('does not show parse result or step 2 content on initial load', () => {
    renderPage()
    expect(screen.queryByTestId('step2-placeholder')).not.toBeInTheDocument()
    expect(screen.queryByTestId('step3-placeholder')).not.toBeInTheDocument()
  })

  it('Interpret Rule button is disabled when rule text is empty', () => {
    renderPage()
    expect(screen.getByTestId('interpret-btn')).toBeDisabled()
  })

  it('advances to Step 2 after successful parse', async () => {
    const { parseRule } = await import('@/services/nlRuleBuilderService')
    vi.mocked(parseRule).mockResolvedValueOnce({
      request_id: 'req-1',
      parse_result_id: 'pr-1',
      parsed_rule: {
        schema_version: '1.0',
        rule_type: 'null_check',
        subject: { raw_text: 'customer_id' },
        operator: 'is_not_null',
        object: null,
        scope: {},
        conditions: [],
        constraints: [],
        confidence: 0.92,
        requires_disambiguation: false,
        parse_warnings: [],
      },
      status: 'parsed',
      reason: null,
      suggestions: [],
      check_configs: [
        {
          check_dimension: 'completeness',
          check_subtype: 'null_check',
          columns: ['customer_id'],
          dataset_id: null,
          dataset_name: null,
          config: {},
          thresholds: { threshold_pass: 95, threshold_warn: 90, null_handling: 'skip', include_empty_strings: false },
          severity: 'high',
          rule_name: 'customer_id must not be null',
          description: null,
        },
      ],
    })

    renderPage()
    const textarea = screen.getByLabelText(/business rule/i)
    await userEvent.type(textarea, 'customer_id must not be null')
    await userEvent.click(screen.getByTestId('interpret-btn'))

    // After successful parse, step 2 content should appear
    expect(await screen.findByTestId('step2-review')).toBeInTheDocument()
    // Step 1 input should be hidden
    expect(screen.queryByTestId('interpret-btn')).not.toBeInTheDocument()
  })
})

describe('NLRuleBuilder page — F127 P04 integration', () => {
  it('advances from Step 2 to Step 3 on "Continue"', async () => {
    const { parseRule } = await import('@/services/nlRuleBuilderService')
    vi.mocked(parseRule).mockResolvedValueOnce({
      request_id: 'req-2',
      parse_result_id: 'pr-2',
      parsed_rule: {
        schema_version: '1.0',
        rule_type: 'null_check',
        subject: { raw_text: 'email' },
        operator: 'is_not_null',
        object: null,
        scope: {},
        conditions: [],
        constraints: [],
        confidence: 0.88,
        requires_disambiguation: false,
        parse_warnings: [],
      },
      status: 'parsed',
      reason: null,
      suggestions: [],
      check_configs: [
        {
          check_dimension: 'completeness',
          check_subtype: 'null_check',
          columns: ['email'],
          dataset_id: null,
          dataset_name: null,
          config: {},
          thresholds: { threshold_pass: 95, threshold_warn: 90, null_handling: 'skip', include_empty_strings: false },
          severity: 'medium',
          rule_name: 'email must not be null',
          description: null,
        },
      ],
    })

    renderPage()
    const textarea = screen.getByLabelText(/business rule/i)
    await userEvent.type(textarea, 'email must not be null')
    await userEvent.click(screen.getByTestId('interpret-btn'))
    await screen.findByTestId('step2-review')
    await userEvent.click(screen.getByTestId('step2-continue-btn'))
    expect(await screen.findByTestId('step3-confirm')).toBeInTheDocument()
  })

  it('navigates back from Step 2 to Step 1 on "Back"', async () => {
    const { parseRule } = await import('@/services/nlRuleBuilderService')
    vi.mocked(parseRule).mockResolvedValueOnce({
      request_id: 'req-3',
      parse_result_id: 'pr-3',
      parsed_rule: {
        schema_version: '1.0',
        rule_type: 'null_check',
        subject: { raw_text: 'order_id' },
        operator: 'is_not_null',
        object: null,
        scope: {},
        conditions: [],
        constraints: [],
        confidence: 0.9,
        requires_disambiguation: false,
        parse_warnings: [],
      },
      status: 'parsed',
      reason: null,
      suggestions: [],
      check_configs: [],
    })

    renderPage()
    const textarea = screen.getByLabelText(/business rule/i)
    await userEvent.type(textarea, 'order_id must not be null')
    await userEvent.click(screen.getByTestId('interpret-btn'))
    await screen.findByTestId('step2-review')
    await userEvent.click(screen.getByTestId('step2-back-btn'))
    expect(await screen.findByTestId('interpret-btn')).toBeInTheDocument()
  })

  it('shows clarification panel in Step 2 when parse status is needs_clarification', async () => {
    const { parseRule } = await import('@/services/nlRuleBuilderService')
    vi.mocked(parseRule).mockResolvedValueOnce({
      request_id: 'req-4',
      parse_result_id: null,
      parsed_rule: null,
      status: 'needs_clarification',
      reason: null,
      suggestions: [],
      clarifying_questions: [
        { field: 'dataset', question: 'Which dataset?', options: ['orders', 'customers'], required: true },
      ],
      clarification_context: 'Ambiguous dataset reference.',
      check_configs: null,
    })

    renderPage()
    const textarea = screen.getByLabelText(/business rule/i)
    await userEvent.type(textarea, 'some ambiguous rule')
    await userEvent.click(screen.getByTestId('interpret-btn'))
    await screen.findByTestId('step2-review')
    expect(screen.getByTestId('clarification-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('step2-continue-btn')).not.toBeInTheDocument()
  })

  it('shows empty-configs warning in Step 3 when check_configs is empty', async () => {
    const { parseRule } = await import('@/services/nlRuleBuilderService')
    vi.mocked(parseRule).mockResolvedValueOnce({
      request_id: 'req-5',
      parse_result_id: 'pr-5',
      parsed_rule: {
        schema_version: '1.0',
        rule_type: 'null_check',
        subject: { raw_text: 'x' },
        operator: 'is_not_null',
        object: null,
        scope: {},
        conditions: [],
        constraints: [],
        confidence: 0.5,
        requires_disambiguation: false,
        parse_warnings: [],
      },
      status: 'parsed',
      reason: null,
      suggestions: [],
      check_configs: [],
    })

    renderPage()
    const textarea = screen.getByLabelText(/business rule/i)
    await userEvent.type(textarea, 'x must not be null')
    await userEvent.click(screen.getByTestId('interpret-btn'))
    await screen.findByTestId('step2-review')
    await userEvent.click(screen.getByTestId('step2-continue-btn'))
    await screen.findByTestId('step3-confirm')
    expect(screen.getByTestId('compiled-config-empty')).toBeInTheDocument()
    expect(screen.getByTestId('submit-proposal-btn')).toBeDisabled()
  })
})
