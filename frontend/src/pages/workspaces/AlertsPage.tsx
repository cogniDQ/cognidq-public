/**
 * AlertsPage — workspace-scoped alerts configuration (F080)
 *
 * Route: /hub/ws/:workspace_id/alerts
 *
 * Features:
 *   - Two-tab layout: Alert Rules | Alert Channels
 *   - Alert Rules: list, create, toggle enabled, delete (F043)
 *   - Alert Channels: list, create, toggle enabled, delete (F044)
 *   - Write actions restricted to alerts:write roles (workspace_administrator, data_engineer)
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, Plus, Trash2, X, Mail, Webhook, MessageSquare, ToggleLeft, ToggleRight, Send, Pencil } from 'lucide-react';
import toast from 'react-hot-toast';

import EmptyState from '../../components/common/EmptyState';
import {
  listAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
  listAlertChannels,
  createAlertChannel,
  updateAlertChannel,
  deleteAlertChannel,
  testAlertChannel,
  ALERT_TRIGGER_TYPES,
  TRIGGER_TYPE_LABELS,
  CHANNEL_TYPE_LABELS,
} from '../../services/alertsService';
import type {
  AlertRule,
  AlertChannel,
  AlertTriggerType,
  AlertChannelType,
  CreateAlertRuleRequest,
  CreateAlertChannelRequest,
} from '../../services/alertsService';
import { listWorkspaceMembers } from '../../services/workspaceMembers';
import type { WorkspaceMemberItem } from '../../services/workspaceMembers';
import { getActorRole } from '../../utils/jwt';
import AlertsDashboard from '../../components/alerts/AlertsDashboard';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const STALE_TIME = 30_000;

type Tab = 'dashboard' | 'rules' | 'channels';

// ─────────────────────────────────────────────────────────────────────────────
// Create / Edit Alert Rule Modal
// ─────────────────────────────────────────────────────────────────────────────

interface RuleModalProps {
  workspaceId: string;
  members: WorkspaceMemberItem[];
  channels: AlertChannel[];
  existingRule?: AlertRule | null;
  onClose: () => void;
  onSaved: () => void;
}

function RuleModal({ workspaceId, members, channels, existingRule, onClose, onSaved }: RuleModalProps) {
  const isEdit = !!existingRule;
  const [name, setName] = useState(existingRule?.name ?? '');
  const [triggerType, setTriggerType] = useState<AlertTriggerType>(
    (existingRule?.trigger_type as AlertTriggerType) ?? 'execution_failed',
  );
  const [selectedRecipients, setSelectedRecipients] = useState<string[]>(
    existingRule?.recipient_user_ids ?? [],
  );
  const [selectedChannels, setSelectedChannels] = useState<string[]>(
    existingRule?.channel_ids ?? [],
  );
  const [enabled, setEnabled] = useState(existingRule?.enabled ?? true);
  const [saving, setSaving] = useState(false);

  function toggleRecipient(userId: string) {
    setSelectedRecipients(prev =>
      prev.includes(userId) ? prev.filter(id => id !== userId) : [...prev, userId],
    );
  }
  function toggleChannel(channelId: string) {
    setSelectedChannels(prev =>
      prev.includes(channelId) ? prev.filter(id => id !== channelId) : [...prev, channelId],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { toast.error('Name is required'); return; }
    if (selectedRecipients.length === 0) { toast.error('Select at least one recipient'); return; }

    setSaving(true);
    try {
      const body: CreateAlertRuleRequest = {
        name: name.trim(),
        trigger_type: triggerType,
        recipient_user_ids: selectedRecipients,
        channel_ids: selectedChannels,
        enabled,
      };
      if (isEdit && existingRule) {
        await updateAlertRule(workspaceId, existingRule.id, body);
        toast.success('Alert rule updated');
      } else {
        await createAlertRule(workspaceId, body);
        toast.success('Alert rule created');
      }
      onSaved();
    } catch {
      toast.error(isEdit ? 'Failed to update alert rule' : 'Failed to create alert rule');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" data-testid="alert-rule-modal">
      <div className="w-full max-w-lg rounded-lg border border-gray-700 bg-gray-900 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-gray-700 px-6 py-4 sticky top-0 bg-gray-900">
          <h2 className="text-lg font-semibold text-white">{isEdit ? 'Edit Alert Rule' : 'New Alert Rule'}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 px-6 py-5">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Notify on execution failure"
              className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              data-testid="alert-rule-name"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">Trigger</label>
            <select
              value={triggerType}
              onChange={e => setTriggerType(e.target.value as AlertTriggerType)}
              className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
              data-testid="alert-rule-trigger"
            >
              {ALERT_TRIGGER_TYPES.map(t => (
                <option key={t} value={t}>{TRIGGER_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">
              Recipients ({selectedRecipients.length} selected)
            </label>
            <div className="max-h-40 overflow-y-auto rounded border border-gray-600 bg-gray-800">
              {members.length === 0 ? (
                <p className="px-3 py-2 text-sm text-gray-500">No workspace members found</p>
              ) : (
                members.map(m => (
                  <label
                    key={m.user_id}
                    className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-gray-700 transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedRecipients.includes(m.user_id)}
                      onChange={() => toggleRecipient(m.user_id)}
                      className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-200">{m.display_name}</span>
                    <span className="text-xs text-gray-500">{m.email}</span>
                  </label>
                ))
              )}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">
              Channels ({selectedChannels.length} selected)
              <span className="ml-2 text-xs text-gray-500 font-normal">— leave empty to use all enabled channels</span>
            </label>
            <div className="max-h-40 overflow-y-auto rounded border border-gray-600 bg-gray-800">
              {channels.length === 0 ? (
                <p className="px-3 py-2 text-sm text-gray-500">No channels configured. Create one in the Channels tab first.</p>
              ) : (
                channels.map(ch => (
                  <label
                    key={ch.id}
                    className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-gray-700 transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedChannels.includes(ch.id)}
                      onChange={() => toggleChannel(ch.id)}
                      className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-200">{ch.name}</span>
                    <span className="text-xs text-gray-500">{CHANNEL_TYPE_LABELS[ch.channel_type]}</span>
                    {!ch.enabled && <span className="text-xs text-amber-400">(disabled)</span>}
                  </label>
                ))
              )}
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              checked={enabled}
              onChange={e => setEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-300">Enabled</span>
          </label>

          <div className="flex justify-end gap-3 border-t border-gray-700 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-300 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              data-testid="alert-rule-save"
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Rule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Create / Edit Alert Channel Modal
// ─────────────────────────────────────────────────────────────────────────────

interface ChannelModalProps {
  workspaceId: string;
  existingChannel?: AlertChannel | null;
  onClose: () => void;
  onSaved: () => void;
}

function ChannelModal({ workspaceId, existingChannel, onClose, onSaved }: ChannelModalProps) {
  const isEdit = !!existingChannel;
  const cfg = (existingChannel?.configuration ?? {}) as Record<string, unknown>;
  const [name, setName] = useState(existingChannel?.name ?? '');
  const [channelType, setChannelType] = useState<AlertChannelType>(
    (existingChannel?.channel_type as AlertChannelType) ?? 'email',
  );
  const [emailAddress, setEmailAddress] = useState(String(cfg.address ?? ''));
  const [webhookUrl, setWebhookUrl] = useState(String(cfg.url ?? ''));
  const [webhookSecret, setWebhookSecret] = useState(String(cfg.secret ?? ''));
  const [slackWebhookUrl, setSlackWebhookUrl] = useState(String(cfg.webhook_url ?? ''));
  const [slackChannel, setSlackChannel] = useState(String(cfg.channel ?? ''));
  const [enabled, setEnabled] = useState(existingChannel?.enabled ?? true);
  const [saving, setSaving] = useState(false);

  function buildConfiguration(): Record<string, unknown> {
    if (channelType === 'email') return { address: emailAddress.trim() };
    if (channelType === 'slack') {
      return {
        webhook_url: slackWebhookUrl.trim(),
        ...(slackChannel.trim() ? { channel: slackChannel.trim() } : {}),
      };
    }
    return {
      url: webhookUrl.trim(),
      ...(webhookSecret.trim() ? { secret: webhookSecret.trim() } : {}),
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { toast.error('Name is required'); return; }
    if (channelType === 'email' && !emailAddress.trim()) {
      toast.error('Email address is required'); return;
    }
    if (channelType === 'webhook' && !webhookUrl.trim()) {
      toast.error('Webhook URL is required'); return;
    }
    if (channelType === 'slack' && !slackWebhookUrl.trim()) {
      toast.error('Slack webhook URL is required'); return;
    }

    setSaving(true);
    try {
      const body: CreateAlertChannelRequest = {
        name: name.trim(),
        channel_type: channelType,
        configuration: buildConfiguration(),
        enabled,
      };
      if (isEdit && existingChannel) {
        await updateAlertChannel(workspaceId, existingChannel.id, body);
        toast.success('Alert channel updated');
      } else {
        await createAlertChannel(workspaceId, body);
        toast.success('Alert channel created');
      }
      onSaved();
    } catch {
      toast.error(isEdit ? 'Failed to update alert channel' : 'Failed to create alert channel');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-lg border border-gray-700 bg-gray-900 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-gray-700 px-6 py-4 sticky top-0 bg-gray-900">
          <h2 className="text-lg font-semibold text-white">{isEdit ? 'Edit Alert Channel' : 'New Alert Channel'}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 px-6 py-5">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Engineering Webhook"
              className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">Type</label>
            <select
              value={channelType}
              onChange={e => setChannelType(e.target.value as AlertChannelType)}
              disabled={isEdit}
              className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none disabled:opacity-60"
            >
              <option value="email">Email</option>
              <option value="webhook">Webhook</option>
              <option value="slack">Slack</option>
            </select>
          </div>

          {channelType === 'email' && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-300">Email Address</label>
              <input
                type="email"
                value={emailAddress}
                onChange={e => setEmailAddress(e.target.value)}
                placeholder="alerts@example.com"
                className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
            </div>
          )}
          {channelType === 'webhook' && (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-300">Webhook URL</label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={e => setWebhookUrl(e.target.value)}
                  placeholder="https://hooks.example.com/..."
                  className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-300">
                  Secret <span className="text-gray-500">(optional)</span>
                </label>
                <input
                  type="text"
                  value={webhookSecret}
                  onChange={e => setWebhookSecret(e.target.value)}
                  placeholder="Signing secret for HMAC verification"
                  className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </>
          )}
          {channelType === 'slack' && (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-300">Slack Incoming Webhook URL</label>
                <input
                  type="url"
                  value={slackWebhookUrl}
                  onChange={e => setSlackWebhookUrl(e.target.value)}
                  placeholder="https://hooks.slack.com/services/..."
                  className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Create one at api.slack.com under “Incoming Webhooks”.
                </p>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-300">
                  Channel override <span className="text-gray-500">(optional)</span>
                </label>
                <input
                  type="text"
                  value={slackChannel}
                  onChange={e => setSlackChannel(e.target.value)}
                  placeholder="#dq-alerts"
                  className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </>
          )}

          <label className="flex cursor-pointer items-center gap-3">
            <input
              type="checkbox"
              checked={enabled}
              onChange={e => setEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-300">Enabled</span>
          </label>

          <div className="flex justify-end gap-3 border-t border-gray-700 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-300 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Channel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Channel config summary helper
// ─────────────────────────────────────────────────────────────────────────────

function channelConfigSummary(ch: AlertChannel): string {
  if (ch.channel_type === 'email') {
    const addr = ch.configuration['address'] ?? ch.configuration['addresses'];
    return addr ? String(addr) : '—';
  }
  if (ch.channel_type === 'webhook') {
    const url = ch.configuration['url'];
    return url ? String(url) : '—';
  }
  if (ch.channel_type === 'slack') {
    const url = ch.configuration['webhook_url'] ?? ch.configuration['url'];
    return url ? String(url) : '—';
  }
  return '—';
}

function channelTypeIcon(t: AlertChannelType) {
  if (t === 'email') return <Mail className="h-3 w-3" />;
  if (t === 'slack') return <MessageSquare className="h-3 w-3" />;
  return <Webhook className="h-3 w-3" />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [showCreateRule, setShowCreateRule] = useState(false);
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [editingChannel, setEditingChannel] = useState<AlertChannel | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);

  const token = localStorage.getItem('access_token');
  const actorRole = getActorRole(token);
  const canWrite =
    actorRole === 'workspace_administrator' ||
    actorRole === 'data_engineer' ||
    actorRole === 'tenant_admin' ||
    actorRole === 'platform_admin';

  // ── Data fetching ──────────────────────────────────────────────────────────

  const { data: rules = [], isLoading: rulesLoading, isError: rulesError, refetch: refetchRules } = useQuery({
    queryKey: ['alert-rules', workspace_id],
    queryFn: () => listAlertRules(workspace_id!),
    enabled: !!workspace_id,
    staleTime: STALE_TIME,
  });

  const { data: channels = [], isLoading: channelsLoading, isError: channelsError, refetch: refetchChannels } = useQuery({
    queryKey: ['alert-channels', workspace_id],
    queryFn: () => listAlertChannels(workspace_id!),
    enabled: !!workspace_id,
    staleTime: STALE_TIME,
  });

  const { data: membersResp } = useQuery({
    queryKey: ['workspace-members', workspace_id],
    queryFn: () => listWorkspaceMembers(workspace_id!),
    enabled: !!workspace_id && canWrite,
    staleTime: 60_000,
  });
  const members = membersResp?.members ?? [];

  // ── Handlers ───────────────────────────────────────────────────────────────

  async function handleDeleteRule(ruleId: string) {
    if (!window.confirm('Delete this alert rule?')) return;
    setDeletingId(ruleId);
    try {
      await deleteAlertRule(workspace_id!, ruleId);
      toast.success('Alert rule deleted');
      queryClient.invalidateQueries({ queryKey: ['alert-rules', workspace_id] });
    } catch {
      toast.error('Failed to delete alert rule');
    } finally {
      setDeletingId(null);
    }
  }

  async function handleToggleRule(rule: AlertRule) {
    setTogglingId(rule.id);
    try {
      await updateAlertRule(workspace_id!, rule.id, { enabled: !rule.enabled });
      queryClient.invalidateQueries({ queryKey: ['alert-rules', workspace_id] });
    } catch {
      toast.error('Failed to update alert rule');
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDeleteChannel(channelId: string) {
    if (!window.confirm('Delete this alert channel?')) return;
    setDeletingId(channelId);
    try {
      await deleteAlertChannel(workspace_id!, channelId);
      toast.success('Alert channel deleted');
      queryClient.invalidateQueries({ queryKey: ['alert-channels', workspace_id] });
    } catch {
      toast.error('Failed to delete alert channel');
    } finally {
      setDeletingId(null);
    }
  }

  async function handleToggleChannel(channel: AlertChannel) {
    setTogglingId(channel.id);
    try {
      await updateAlertChannel(workspace_id!, channel.id, { enabled: !channel.enabled });
      queryClient.invalidateQueries({ queryKey: ['alert-channels', workspace_id] });
    } catch {
      toast.error('Failed to update alert channel');
    } finally {
      setTogglingId(null);
    }
  }

  async function handleTestChannel(channelId: string) {
    setTestingId(channelId);
    try {
      const result = await testAlertChannel(workspace_id!, channelId);
      if (result.success) {
        toast.success('Test notification sent successfully');
      } else {
        toast.error(result.message || 'Test notification failed');
      }
    } catch {
      toast.error('Failed to send test notification');
    } finally {
      setTestingId(null);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-950 p-6 text-white">
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bell className="h-6 w-6 text-blue-400" />
          <h1 className="text-2xl font-bold text-white">Alerts</h1>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 rounded-lg border border-gray-700 bg-gray-900 p-1 w-fit">
        {(['dashboard', 'rules', 'channels'] as Tab[]).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            data-testid={`alerts-tab-${tab}`}
            className={`rounded px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab === 'dashboard' ? 'Dashboard' : tab === 'rules' ? 'Alert Rules' : 'Alert Channels'}
          </button>
        ))}
      </div>

      {/* ── Dashboard Tab ─────────────────────────────────────── */}
      {activeTab === 'dashboard' && workspace_id && (
        <AlertsDashboard workspaceId={workspace_id} />
      )}

      {/* ── Alert Rules Tab ───────────────────────────────────────────────── */}
      {activeTab === 'rules' && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-gray-400">
              {rules.length} rule{rules.length !== 1 ? 's' : ''} configured
            </p>
            {canWrite && (
              <button
                onClick={() => setShowCreateRule(true)}
                data-testid="alert-new-rule-btn"
                className="flex items-center gap-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
              >
                <Plus className="h-4 w-4" /> New Rule
              </button>
            )}
          </div>

          {rulesLoading && (
            <p className="text-sm text-gray-500">Loading alert rules…</p>
          )}
          {rulesError && (
            <EmptyState
              variant="error"
              title="Couldn't load alert rules"
              description="We couldn't reach the alerts service. Try again or check your connection."
              onRetry={() => refetchRules()}
              testId="alert-rules-error"
            />
          )}
          {!rulesLoading && !rulesError && rules.length === 0 && (
            <EmptyState
              icon={Bell}
              title="No alert rules yet"
              description="Alert rules notify the right people when issues, incidents, or flow failures occur. Pair them with a channel to dispatch via email or webhook."
              primaryAction={canWrite ? {
                label: 'Create alert rule',
                onClick: () => setShowCreateRule(true),
                icon: Plus,
              } : undefined}
              testId="alert-rules-empty"
            />
          )}
          {!rulesLoading && rules.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-700">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 bg-gray-900">
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Name</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Trigger</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Recipients</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Status</th>
                    {canWrite && (
                      <th className="px-4 py-3 text-right font-medium text-gray-400">Actions</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule, i) => (
                    <tr
                      key={rule.id}
                      className={`border-b border-gray-800 transition-colors hover:bg-gray-800/40 ${
                        i % 2 === 0 ? 'bg-gray-900/30' : 'bg-gray-900/10'
                      }`}
                    >
                      <td className="px-4 py-3 font-medium text-white">{rule.name}</td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300 border border-gray-700">
                          {TRIGGER_TYPE_LABELS[rule.trigger_type]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {rule.recipient_user_ids.length}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          rule.enabled
                            ? 'bg-green-900/50 text-green-300 border border-green-700'
                            : 'bg-gray-700/50 text-gray-400 border border-gray-600'
                        }`}>
                          {rule.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </td>
                      {canWrite && (
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => setEditingRule(rule)}
                              title="Edit rule"
                              className="text-gray-400 hover:text-blue-400 transition-colors"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleToggleRule(rule)}
                              disabled={togglingId === rule.id}
                              title={rule.enabled ? 'Disable rule' : 'Enable rule'}
                              className="text-gray-400 hover:text-white disabled:opacity-40 transition-colors"
                            >
                              {rule.enabled
                                ? <ToggleRight className="h-5 w-5 text-green-400" />
                                : <ToggleLeft className="h-5 w-5" />}
                            </button>
                            <button
                              onClick={() => handleDeleteRule(rule.id)}
                              disabled={deletingId === rule.id}
                              title="Delete rule"
                              className="text-gray-500 hover:text-red-400 disabled:opacity-40 transition-colors"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Alert Channels Tab ────────────────────────────────────────────── */}
      {activeTab === 'channels' && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-gray-400">
              {channels.length} channel{channels.length !== 1 ? 's' : ''} configured
            </p>
            {canWrite && (
              <button
                onClick={() => setShowCreateChannel(true)}
                className="flex items-center gap-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
              >
                <Plus className="h-4 w-4" /> New Channel
              </button>
            )}
          </div>

          {channelsLoading && (
            <p className="text-sm text-gray-500">Loading alert channels…</p>
          )}
          {channelsError && (
            <EmptyState
              variant="error"
              title="Couldn't load alert channels"
              description="We couldn't reach the channels service. Try again or check your connection."
              onRetry={() => refetchChannels()}
              testId="alert-channels-error"
            />
          )}
          {!channelsLoading && !channelsError && channels.length === 0 && (
            <EmptyState
              icon={Mail}
              title="No alert channels yet"
              description="Channels are the destinations alert rules dispatch to — a team email, a Slack webhook, or a PagerDuty endpoint. Add one before creating rules that fire to it."
              primaryAction={canWrite ? {
                label: 'Create channel',
                onClick: () => setShowCreateChannel(true),
                icon: Plus,
              } : undefined}
              testId="alert-channels-empty"
            />
          )}
          {!channelsLoading && channels.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-700">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 bg-gray-900">
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Name</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Type</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Destination</th>
                    <th className="px-4 py-3 text-left font-medium text-gray-400">Status</th>
                    {canWrite && (
                      <th className="px-4 py-3 text-right font-medium text-gray-400">Actions</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {channels.map((ch, i) => (
                    <tr
                      key={ch.id}
                      className={`border-b border-gray-800 transition-colors hover:bg-gray-800/40 ${
                        i % 2 === 0 ? 'bg-gray-900/30' : 'bg-gray-900/10'
                      }`}
                    >
                      <td className="px-4 py-3 font-medium text-white">{ch.name}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5 rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300 border border-gray-700">
                          {channelTypeIcon(ch.channel_type)}
                          {CHANNEL_TYPE_LABELS[ch.channel_type]}
                        </span>
                      </td>
                      <td className="max-w-xs truncate px-4 py-3 text-gray-400 font-mono text-xs">
                        {channelConfigSummary(ch)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          ch.enabled
                            ? 'bg-green-900/50 text-green-300 border border-green-700'
                            : 'bg-gray-700/50 text-gray-400 border border-gray-600'
                        }`}>
                          {ch.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </td>
                      {canWrite && (
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleTestChannel(ch.id)}
                              disabled={testingId === ch.id}
                              title="Send test notification"
                              className="text-gray-400 hover:text-blue-400 disabled:opacity-40 transition-colors"
                            >
                              <Send className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => setEditingChannel(ch)}
                              title="Edit channel"
                              className="text-gray-400 hover:text-blue-400 transition-colors"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleToggleChannel(ch)}
                              disabled={togglingId === ch.id}
                              title={ch.enabled ? 'Disable channel' : 'Enable channel'}
                              className="text-gray-400 hover:text-white disabled:opacity-40 transition-colors"
                            >
                              {ch.enabled
                                ? <ToggleRight className="h-5 w-5 text-green-400" />
                                : <ToggleLeft className="h-5 w-5" />}
                            </button>
                            <button
                              onClick={() => handleDeleteChannel(ch.id)}
                              disabled={deletingId === ch.id}
                              title="Delete channel"
                              className="text-gray-500 hover:text-red-400 disabled:opacity-40 transition-colors"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {(showCreateRule || editingRule) && (
        <RuleModal
          workspaceId={workspace_id!}
          members={members}
          channels={channels}
          existingRule={editingRule}
          onClose={() => {
            setShowCreateRule(false);
            setEditingRule(null);
          }}
          onSaved={() => {
            setShowCreateRule(false);
            setEditingRule(null);
            queryClient.invalidateQueries({ queryKey: ['alert-rules', workspace_id] });
          }}
        />
      )}
      {(showCreateChannel || editingChannel) && (
        <ChannelModal
          workspaceId={workspace_id!}
          existingChannel={editingChannel}
          onClose={() => {
            setShowCreateChannel(false);
            setEditingChannel(null);
          }}
          onSaved={() => {
            setShowCreateChannel(false);
            setEditingChannel(null);
            queryClient.invalidateQueries({ queryKey: ['alert-channels', workspace_id] });
          }}
        />
      )}
    </div>
  );
}
