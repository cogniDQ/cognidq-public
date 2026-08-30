/**
 * Shared test fixtures for F127 NL Rule Builder UI Redesign tests.
 */
import type {
  ParseRuleResponse,
  ParseExplanationItem,
  ParseTrustSummary,
  DecompositionSummary,
  CheckConfigOutput,
  ClarifyingQuestion,
} from '@/types/nlRuleBuilder'

export const mockExplainabilityItems: ParseExplanationItem[] = [
  {
    topic: 'rule_type',
    decision: 'null_check',
    evidence: ['keyword: null', 'subject: customer_id'],
    confidence_impact: 0.3,
    caveat: null,
  },
  {
    topic: 'subject',
    decision: 'customer_id',
    evidence: ['glossary match: customer_id (score 0.95)'],
    confidence_impact: 0.2,
    caveat: 'Resolved via glossary',
  },
]

export const mockTrustSummary: ParseTrustSummary = {
  confidence_band: 'high',
  confidence_score: 0.92,
  caveats: [],
  assumptions: ['Column resolved via glossary'],
  recommendation: 'Accept',
}

export const mockLowTrustSummary: ParseTrustSummary = {
  confidence_band: 'low',
  confidence_score: 0.38,
  caveats: ['Subject ambiguous', 'No glossary match'],
  assumptions: [],
  recommendation: 'Review manually',
}

export const mockDecompositionSummary: DecompositionSummary = {
  count: 2,
  logic: 'AND',
  obligations: ['customer_id must not be null', 'email must not be null'],
}

export const mockSingleDecomposition: DecompositionSummary = {
  count: 1,
  logic: null,
  obligations: ['customer_id must not be null'],
}

export const mockCheckConfigs: CheckConfigOutput[] = [
  {
    check_dimension: 'completeness',
    check_subtype: 'null_check',
    columns: ['customer_id'],
    dataset_id: null,
    dataset_name: null,
    config: {},
    thresholds: {
      threshold_pass: 95,
      threshold_warn: 90,
      null_handling: 'skip',
      include_empty_strings: false,
    },
    severity: 'high',
    rule_name: 'customer_id must not be null',
    description: null,
  },
]

export const mockClarifyingQuestions: ClarifyingQuestion[] = [
  {
    field: 'dataset',
    question: 'Which dataset does this rule apply to?',
    options: ['orders', 'customers'],
    required: true,
  },
]

export const mockParsedResponse: ParseRuleResponse = {
  request_id: 'req-001',
  parse_result_id: 'pr-001',
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
    clarifying_questions: [],
  },
  status: 'parsed',
  reason: null,
  suggestions: [],
  check_configs: mockCheckConfigs,
  explainability: mockExplainabilityItems,
  trust_summary: mockTrustSummary,
  decomposition_summary: { count: 1, logic: null, obligations: ['customer_id must not be null'] },
}

export const mockClarificationResponse: ParseRuleResponse = {
  request_id: 'req-002',
  parse_result_id: null,
  parsed_rule: null,
  status: 'needs_clarification',
  reason: null,
  suggestions: [],
  clarifying_questions: mockClarifyingQuestions,
  clarification_context: 'The parser could not determine the target dataset.',
  check_configs: null,
}

export const mockCompoundParsedResponse: ParseRuleResponse = {
  ...mockParsedResponse,
  decomposition_summary: mockDecompositionSummary,
  parsed_rule: {
    ...(mockParsedResponse.parsed_rule as NonNullable<ParseRuleResponse['parsed_rule']>),
    is_compound: true,
    obligation_logic: 'AND',
  },
}
