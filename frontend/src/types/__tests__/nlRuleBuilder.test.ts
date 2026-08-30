/**
 * Unit tests for NL rule builder TypeScript types
 * Validates type shapes, enum values, and DEFAULT_DRAFT constant.
 */
import { describe, it, expect } from 'vitest'
import { DEFAULT_DRAFT } from '@/types/nlRuleBuilder'
import type {
  RuleType,
  SIREntity,
  SIRCondition,
  SIRScope,
  StructuredIntermediateRepresentation,
  ParseRuleRequest,
  ParseRuleResponse,
  NLRuleDraft,
  RecentParseEntry,
} from '@/types/nlRuleBuilder'
import type {
  SignalBreakdown,
  ResolutionCandidate,
  EntityResolution,
  ResolveRequest,
  ResolveResponse,
} from '@/types/resolution'

describe('nlRuleBuilder types', () => {
  describe('DEFAULT_DRAFT', () => {
    it('has empty rule_text', () => {
      expect(DEFAULT_DRAFT.rule_text).toBe('')
    })

    it('has empty dataset_id', () => {
      expect(DEFAULT_DRAFT.dataset_id).toBe('')
    })

    it('has empty domain', () => {
      expect(DEFAULT_DRAFT.domain).toBe('')
    })

    it('has medium severity', () => {
      expect(DEFAULT_DRAFT.severity).toBe('medium')
    })

    it('has empty tags', () => {
      expect(DEFAULT_DRAFT.tags).toEqual([])
    })

    it('has use_context false', () => {
      expect(DEFAULT_DRAFT.use_context).toBe(false)
    })
  })

  describe('type shape validation', () => {
    it('NLRuleDraft shape matches DEFAULT_DRAFT', () => {
      const draft: NLRuleDraft = DEFAULT_DRAFT
      expect(draft).toHaveProperty('rule_text')
      expect(draft).toHaveProperty('dataset_id')
      expect(draft).toHaveProperty('domain')
      expect(draft).toHaveProperty('severity')
      expect(draft).toHaveProperty('tags')
      expect(draft).toHaveProperty('use_context')
    })

    it('ParseRuleRequest requires rule_text', () => {
      const req: ParseRuleRequest = { rule_text: 'test' }
      expect(req.rule_text).toBe('test')
      expect(req.severity).toBeUndefined()
      expect(req.tags).toBeUndefined()
      expect(req.context).toBeUndefined()
    })

    it('ParseRuleRequest with all fields', () => {
      const req: ParseRuleRequest = {
        rule_text: 'email not null',
        severity: 'high',
        tags: ['tag1'],
        context: { dataset_id: 'ds-1', domain: 'Finance' },
      }
      expect(req.context?.dataset_id).toBe('ds-1')
    })

    it('RecentParseEntry shape', () => {
      const entry: RecentParseEntry = {
        rule_text: 'test',
        confidence: 0.9,
        rule_type: 'not_null',
        timestamp: '2024-01-01T00:00:00Z',
      }
      expect(entry.rule_type).toBe('not_null')
    })

    it('SignalBreakdown shape', () => {
      const sb: SignalBreakdown = {
        signal_name: 'lexical',
        score: 0.9,
        evidence: 'match',
      }
      expect(sb.score).toBe(0.9)
    })

    it('ResolutionCandidate shape', () => {
      const rc: ResolutionCandidate = {
        asset_id: 'a1',
        column_name: 'email',
        overall_score: 0.85,
        confidence_band: 'medium',
        signal_breakdown: [],
        evidence_summary: [],
      }
      expect(rc.column_name).toBe('email')
      expect(rc.dataset_name).toBeUndefined()
    })

    it('EntityResolution shape', () => {
      const er: EntityResolution = {
        raw_text: 'email',
        candidates: [],
        best_candidate: null,
        requires_disambiguation: false,
      }
      expect(er.requires_disambiguation).toBe(false)
    })

    it('ResolveRequest minimal shape', () => {
      const req: ResolveRequest = { parsed_rule: {} }
      expect(req.selected_candidates).toBeUndefined()
    })

    it('ResolveResponse shape', () => {
      const resp: ResolveResponse = {
        resolved_rule: {},
        subject_resolution: {
          raw_text: 'x',
          candidates: [],
          best_candidate: null,
          requires_disambiguation: false,
        },
        object_resolution: null,
        overall_confidence: 0.9,
        requires_disambiguation: false,
        resolution_evidence: {},
      }
      expect(resp.object_resolution).toBeNull()
    })
  })

  describe('RuleType values', () => {
    it('all rule types are valid strings', () => {
      const validTypes: RuleType[] = [
        'null_check', 'not_null', 'column_comparison', 'numeric_threshold',
        'date_comparison', 'value_in_list', 'regex_format', 'length_check',
        'uniqueness', 'composite_uniqueness', 'reference_lookup',
        'conditional_rule', 'arithmetic_comparison', 'unknown',
      ]
      expect(validTypes).toHaveLength(14)
    })
  })
})
