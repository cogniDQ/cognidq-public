/**
 * Unit tests for nlRuleBuilderService
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { parseRule, resolveRule } from '@/services/nlRuleBuilderService'

// Mock the api module
vi.mock('@/services/api', () => ({
  api: {
    post: vi.fn(),
  },
}))

import { api } from '@/services/api'

const mockPost = vi.mocked(api.post)

describe('nlRuleBuilderService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('parseRule', () => {
    it('calls correct endpoint', async () => {
      mockPost.mockResolvedValue({ data: { request_id: 'r1' } })
      await parseRule('ws-1', { rule_text: 'test' })
      expect(mockPost).toHaveBeenCalledWith(
        '/workspaces/ws-1/rule-builder/parse',
        { rule_text: 'test' }
      )
    })

    it('returns response data', async () => {
      const mockData = { request_id: 'r1', confidence: 0.95 }
      mockPost.mockResolvedValue({ data: mockData })
      const result = await parseRule('ws-1', { rule_text: 'test' })
      expect(result).toEqual(mockData)
    })

    it('passes full payload with context', async () => {
      mockPost.mockResolvedValue({ data: {} })
      await parseRule('ws-1', {
        rule_text: 'email must not be null',
        severity: 'high',
        tags: ['finance'],
        context: { dataset_id: 'ds-1', domain: 'Finance' },
      })
      expect(mockPost).toHaveBeenCalledWith(
        '/workspaces/ws-1/rule-builder/parse',
        {
          rule_text: 'email must not be null',
          severity: 'high',
          tags: ['finance'],
          context: { dataset_id: 'ds-1', domain: 'Finance' },
        }
      )
    })

    it('propagates errors', async () => {
      mockPost.mockRejectedValue(new Error('Network error'))
      await expect(parseRule('ws-1', { rule_text: 'test' })).rejects.toThrow('Network error')
    })

    it('uses workspace id in URL', async () => {
      mockPost.mockResolvedValue({ data: {} })
      await parseRule('my-workspace-42', { rule_text: 'test' })
      expect(mockPost.mock.calls[0][0]).toBe('/workspaces/my-workspace-42/rule-builder/parse')
    })
  })

  describe('resolveRule', () => {
    it('calls correct endpoint', async () => {
      mockPost.mockResolvedValue({ data: {} })
      await resolveRule('ws-1', { parsed_rule: {} })
      expect(mockPost).toHaveBeenCalledWith(
        '/workspaces/ws-1/rule-builder/resolve',
        { parsed_rule: {} }
      )
    })

    it('returns response data', async () => {
      const mockData = { overall_confidence: 0.85, requires_disambiguation: true }
      mockPost.mockResolvedValue({ data: mockData })
      const result = await resolveRule('ws-1', { parsed_rule: {} })
      expect(result).toEqual(mockData)
    })

    it('passes selected_candidates', async () => {
      mockPost.mockResolvedValue({ data: {} })
      await resolveRule('ws-1', {
        parsed_rule: { rule_type: 'not_null' },
        dataset_context: 'orders',
        domain_context: 'finance',
        selected_candidates: { subject: 'asset-1' },
      })
      expect(mockPost).toHaveBeenCalledWith(
        '/workspaces/ws-1/rule-builder/resolve',
        {
          parsed_rule: { rule_type: 'not_null' },
          dataset_context: 'orders',
          domain_context: 'finance',
          selected_candidates: { subject: 'asset-1' },
        }
      )
    })

    it('propagates errors', async () => {
      mockPost.mockRejectedValue(new Error('Server error'))
      await expect(resolveRule('ws-1', { parsed_rule: {} })).rejects.toThrow('Server error')
    })
  })
})
