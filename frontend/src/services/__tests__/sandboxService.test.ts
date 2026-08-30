/**
 * F134 P11 — Unit tests for demoRequestService and adminSandboxService
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  submitDemoRequest,
  getDemoRequestStatus,
} from '@/services/demoRequestService';
import {
  listAdminDemoRequests,
  approveAdminDemoRequest,
  rejectAdminDemoRequest,
  listAdminSandboxes,
  extendSandbox,
  suspendSandbox,
  archiveSandbox,
  deleteSandbox,
  getSandboxUsage,
} from '@/services/adminSandboxService';

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
const mockDelete = vi.mocked(api.delete);

const SANDBOX_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

beforeEach(() => vi.clearAllMocks());

// ── demoRequestService ─────────────────────────────────────────────────────

describe('demoRequestService', () => {
  describe('submitDemoRequest', () => {
    it('posts to /demo-requests', async () => {
      mockPost.mockResolvedValue({ data: { id: 'req-1', status: 'pending' } });
      const result = await submitDemoRequest({
        first_name: 'Jane',
        last_name: 'Smith',
        email: 'jane@acme.com',
        company: 'Acme',
      });
      expect(mockPost).toHaveBeenCalledWith('/demo-requests', expect.any(Object));
      expect(result.id).toBe('req-1');
    });
  });

  describe('getDemoRequestStatus', () => {
    it('calls the correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { id: 'req-1', status: 'approved' } });
      const result = await getDemoRequestStatus('req-1');
      expect(mockGet).toHaveBeenCalledWith('/demo-requests/req-1/status');
      expect(result.status).toBe('approved');
    });
  });
});

// ── adminSandboxService ───────────────────────────────────────────────────────

describe('adminSandboxService', () => {
  describe('listAdminDemoRequests', () => {
    it('calls /admin/demo-requests with params', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0, page: 1, page_size: 20 } });
      await listAdminDemoRequests({ status: 'pending' });
      expect(mockGet).toHaveBeenCalledWith('/admin/demo-requests', {
        params: { status: 'pending' },
      });
    });
  });

  describe('approveAdminDemoRequest', () => {
    it('posts to correct approve URL', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await approveAdminDemoRequest('req-1');
      expect(mockPost).toHaveBeenCalledWith('/admin/demo-requests/req-1/approve', {
        template_id: undefined,
      });
    });
  });

  describe('rejectAdminDemoRequest', () => {
    it('posts rejection with reason', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await rejectAdminDemoRequest('req-1', 'out of scope');
      expect(mockPost).toHaveBeenCalledWith('/admin/demo-requests/req-1/reject', {
        reason: 'out of scope',
      });
    });
  });

  describe('listAdminSandboxes', () => {
    it('calls /admin/sandboxes', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } });
      await listAdminSandboxes({ status: 'active' });
      expect(mockGet).toHaveBeenCalledWith('/admin/sandboxes', {
        params: { status: 'active' },
      });
    });
  });

  describe('extendSandbox', () => {
    it('posts to extend URL', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await extendSandbox(SANDBOX_ID, { note: 'Needs more time' });
      expect(mockPost).toHaveBeenCalledWith(
        `/admin/sandboxes/${SANDBOX_ID}/extend`,
        { note: 'Needs more time' },
      );
    });
  });

  describe('suspendSandbox', () => {
    it('posts to suspend URL with reason', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await suspendSandbox(SANDBOX_ID, { reason: 'abuse' });
      expect(mockPost).toHaveBeenCalledWith(
        `/admin/sandboxes/${SANDBOX_ID}/suspend`,
        { reason: 'abuse' },
      );
    });
  });

  describe('archiveSandbox', () => {
    it('posts to archive URL', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await archiveSandbox(SANDBOX_ID);
      expect(mockPost).toHaveBeenCalledWith(`/admin/sandboxes/${SANDBOX_ID}/archive`);
    });
  });

  describe('deleteSandbox', () => {
    it('sends DELETE with force=false by default', async () => {
      mockDelete.mockResolvedValue({ data: {} });
      await deleteSandbox(SANDBOX_ID);
      expect(mockDelete).toHaveBeenCalledWith(`/admin/sandboxes/${SANDBOX_ID}`, {
        params: { force: false },
      });
    });

    it('sends DELETE with force=true when specified', async () => {
      mockDelete.mockResolvedValue({ data: {} });
      await deleteSandbox(SANDBOX_ID, true);
      expect(mockDelete).toHaveBeenCalledWith(`/admin/sandboxes/${SANDBOX_ID}`, {
        params: { force: true },
      });
    });
  });

  describe('getSandboxUsage', () => {
    it('gets usage from correct endpoint', async () => {
      mockGet.mockResolvedValue({
        data: {
          summary: { total_events: 10, engagement_score: 'medium' },
          events_by_type: [],
          timeline: [],
        },
      });
      const result = await getSandboxUsage(SANDBOX_ID);
      expect(mockGet).toHaveBeenCalledWith(`/admin/sandboxes/${SANDBOX_ID}/usage`);
      expect(result.summary.engagement_score).toBe('medium');
    });
  });
});
