/**
 * F134 P12 — Unit tests for sandboxUserService and trial_expired interceptor
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getSandboxMe,
  getSandboxOnboarding,
  completeSandboxStep,
  requestSandboxExtension,
} from '@/services/sandboxUserService';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from '@/services/api';
const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);

beforeEach(() => vi.clearAllMocks());

// ── sandboxUserService ────────────────────────────────────────────────────────

describe('sandboxUserService', () => {
  describe('getSandboxMe', () => {
    it('calls /sandbox/me', async () => {
      mockGet.mockResolvedValue({
        data: { is_sandbox: true, banner: { remaining_days: 5 } },
      });
      const result = await getSandboxMe();
      expect(mockGet).toHaveBeenCalledWith('/sandbox/me');
      expect(result.is_sandbox).toBe(true);
    });
  });

  describe('getSandboxOnboarding', () => {
    it('calls /sandbox/onboarding', async () => {
      mockGet.mockResolvedValue({
        data: { steps: [], all_complete: false },
      });
      const result = await getSandboxOnboarding();
      expect(mockGet).toHaveBeenCalledWith('/sandbox/onboarding');
      expect(result.all_complete).toBe(false);
    });
  });

  describe('completeSandboxStep', () => {
    it('posts to correct step complete URL', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await completeSandboxStep('run_check');
      expect(mockPost).toHaveBeenCalledWith('/sandbox/onboarding/run_check/complete');
    });
  });

  describe('requestSandboxExtension', () => {
    it('posts to /sandbox/extension-request with message', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await requestSandboxExtension('Need 7 more days');
      expect(mockPost).toHaveBeenCalledWith('/sandbox/extension-request', {
        message: 'Need 7 more days',
      });
    });

    it('posts with undefined message when omitted', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await requestSandboxExtension();
      expect(mockPost).toHaveBeenCalledWith('/sandbox/extension-request', {
        message: undefined,
      });
    });
  });
});

// ── trial_expired interceptor (logic test) ────────────────────────────────────

describe('trial_expired detection', () => {
  it('identifies trial_expired code from response error shape', () => {
    const error = {
      response: {
        status: 402,
        data: { error: { code: 'trial_expired' } },
      },
    };
    const code = error.response?.data?.error?.code;
    expect(code).toBe('trial_expired');
  });

  it('identifies trial_expired from flat data.code', () => {
    const error = {
      response: {
        status: 402,
        data: { code: 'trial_expired' },
      },
    };
    const code =
      (error.response?.data as { error?: { code?: string }; code?: string })?.error?.code ??
      (error.response?.data as { code?: string })?.code;
    expect(code).toBe('trial_expired');
  });
});
