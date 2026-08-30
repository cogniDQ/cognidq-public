import { useState } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import type { SetURLSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowLeft,
  Edit,
  ChevronDown,
  ChevronUp,
  Eye,
  BarChart3 as BarChart3Icon,
  ShieldCheck,
  Network,
} from 'lucide-react';
import DatasetProfilingPanel from '../../components/datasets/DatasetProfilingPanel';
import DatasetPreviewPanel from '../../components/datasets/DatasetPreviewPanel';
import DatasetQualityPanel from '../../components/datasets/DatasetQualityPanel';
import { listRules, type RuleResponse } from '../../services/ruleService';
import {
  getDataset,
  activateDataset,
  deactivateDataset,
  reactivateDataset,
  archiveDataset,
  getDatasetAuditLogs,
} from '../../services/datasetService';
import { getActorRole } from '../../utils/jwt';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';
import type { Dataset, DatasetStatus } from '../../types/dataset';

const STATUS_COLORS: Record<DatasetStatus, string> = {
  draft: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  active: 'text-green-400 bg-green-400/10 border-green-400/30',
  inactive: 'text-gray-400 bg-gray-400/10 border-gray-400/30',
  archived: 'text-red-400 bg-red-400/10 border-red-400/30',
};

const WRITE_ROLES = new Set(['workspace_administrator', 'data_engineer', 'workspace_steward', 'platform_admin']);
const PAUSE_ROLES = new Set(['workspace_administrator', 'data_engineer', 'platform_admin']);

export default function DatasetDetailPage() {
  const { workspace_id, dataset_id } = useParams<{ workspace_id: string; dataset_id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { wsPath } = useTenantScopedPath();
  const [searchParams, setSearchParams] = useSearchParams();
  // F14 — audit-log open state lives in the URL so deep links and reloads
  // preserve the panel visibility (and “Expand audit” shareable links).
  const showAuditLog = searchParams.get('audit') === '1';
  const setShowAuditLog = (next: boolean | ((prev: boolean) => boolean)) => {
    const nv = typeof next === 'function' ? (next as (p: boolean) => boolean)(showAuditLog) : next;
    const sp = new URLSearchParams(searchParams);
    if (nv) sp.set('audit', '1');
    else sp.delete('audit');
    setSearchParams(sp, { replace: true });
  };
  const [showArchiveModal, setShowArchiveModal] = useState(false);

  const token = localStorage.getItem('access_token');
  const role = getActorRole(token);
  const canWrite = WRITE_ROLES.has(role ?? '');
  const canPause = PAUSE_ROLES.has(role ?? '');
  const canArchive = role === 'workspace_administrator' || role === 'platform_admin';

  const queryKey = ['dataset', workspace_id, dataset_id];

  const { data: dataset, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getDataset(workspace_id!, dataset_id!),
    enabled: !!workspace_id && !!dataset_id,
    staleTime: 30_000,
  });

  const { data: auditData, isLoading: auditLoading } = useQuery({
    queryKey: ['dataset-audit', workspace_id, dataset_id],
    queryFn: () => getDatasetAuditLogs(workspace_id!, dataset_id!),
    enabled: showAuditLog && !!workspace_id && !!dataset_id,
    staleTime: 30_000,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey });
  }

  const activateMutation = useMutation({
    mutationFn: () => activateDataset(workspace_id!, dataset_id!),
    onSuccess: () => { toast.success('Dataset activated'); invalidate(); },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error?.message ?? 'Failed to activate');
    },
  });

  const deactivateMutation = useMutation({
    mutationFn: () => deactivateDataset(workspace_id!, dataset_id!),
    onSuccess: () => { toast.success('Dataset deactivated'); invalidate(); },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error?.message ?? 'Failed to deactivate');
    },
  });

  const reactivateMutation = useMutation({
    mutationFn: () => reactivateDataset(workspace_id!, dataset_id!),
    onSuccess: () => { toast.success('Dataset reactivated'); invalidate(); },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error?.message ?? 'Failed to reactivate');
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveDataset(workspace_id!, dataset_id!),
    onSuccess: () => {
      toast.success('Dataset archived');
      setShowArchiveModal(false);
      invalidate();
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error?.message ?? 'Failed to archive');
      setShowArchiveModal(false);
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse" data-testid="dataset-detail-loading">
        <div className="h-8 w-64 rounded-lg bg-gray-800" />
        <div className="h-48 rounded-2xl bg-gray-800/60" />
      </div>
    );
  }

  if (isError || !dataset) {
    return (
      <div data-testid="dataset-detail-error">
        <button onClick={() => navigate(wsPath(workspace_id ?? '', '/datasets'))}
          className="mb-4 flex items-center gap-1 text-sm text-gray-400 hover:text-white">
          <ArrowLeft className="w-4 h-4" /> Back to datasets
        </button>
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
          Failed to load dataset.
        </div>
      </div>
    );
  }

  const status = dataset.status as DatasetStatus;
  const isArchived = status === 'archived';

  return (
    <div className="space-y-6" data-testid="dataset-detail">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            to={wsPath(workspace_id ?? '', '/datasets')}
            className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Datasets
          </Link>
          <h1 className="text-xl font-semibold text-white">{dataset.dataset_name}</h1>
          <span
            data-testid="status-badge"
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_COLORS[status]}`}
          >
            {status.toUpperCase()}
          </span>
          {/* F11 — schema drift badge: warns when the schema has never been
              profiled or has drifted (last_profiled_at older than 7 days).
              Backed only by metadata for now; a real diff against the live
              source can plug in later without UI changes. */}
          <SchemaDriftBadge dataset={dataset} />
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          {canWrite && !isArchived && (
            <Link
              to={wsPath(workspace_id ?? '', `/datasets/${dataset_id}/edit`)}
              data-testid="edit-btn"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-600 text-gray-300 text-sm hover:bg-gray-700 transition-colors"
            >
              <Edit className="w-3.5 h-3.5" />
              Edit
            </Link>
          )}
          {canWrite && status === 'draft' && (
            <button
              data-testid="activate-btn"
              onClick={() => activateMutation.mutate()}
              disabled={activateMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-green-600 text-white text-sm hover:bg-green-500 transition-colors disabled:opacity-50"
            >
              Activate
            </button>
          )}
          {canPause && status === 'active' && (
            <button
              data-testid="deactivate-btn"
              onClick={() => deactivateMutation.mutate()}
              disabled={deactivateMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-yellow-600 text-white text-sm hover:bg-yellow-500 transition-colors disabled:opacity-50"
            >
              Deactivate
            </button>
          )}
          {canWrite && status === 'inactive' && (
            <button
              data-testid="reactivate-btn"
              onClick={() => reactivateMutation.mutate()}
              disabled={reactivateMutation.isPending}
              className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-500 transition-colors disabled:opacity-50"
            >
              Reactivate
            </button>
          )}
          {canArchive && !isArchived && (
            <button
              data-testid="archive-btn"
              onClick={() => setShowArchiveModal(true)}
              className="px-3 py-1.5 rounded-lg bg-red-700 text-white text-sm hover:bg-red-600 transition-colors"
            >
              Archive
            </button>
          )}
        </div>
      </div>

      {/* Metadata card */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-5 grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-gray-400">Dataset Type</p>
          <p className="text-white capitalize">{dataset.dataset_type}</p>
        </div>
        <div>
          <p className="text-gray-400">Physical Identifier</p>
          <p className="text-white font-mono">{dataset.physical_identifier}</p>
        </div>
        <div>
          <p className="text-gray-400">Data Source</p>
          <p className="text-white">{dataset.data_source_name ?? '—'}</p>
        </div>
        <div>
          <p className="text-gray-400">Criticality</p>
          <p className="text-white capitalize">{dataset.criticality}</p>
        </div>
        <div>
          <p className="text-gray-400">Business Domain</p>
          <p className="text-white">{dataset.business_domain ?? '—'}</p>
        </div>
        <div>
          <p className="text-gray-400">Description</p>
          <p className="text-white">
            {(() => {
              // F9 — strip placeholder values left over from bulk
              // registration scripts that wrote "auto" / "—" / empty
              // strings as a description; render an em-dash instead.
              const raw = (dataset.description ?? '').trim();
              const placeholders = new Set(['auto', '-', '—', 'none', 'null']);
              if (!raw || placeholders.has(raw.toLowerCase())) return '—';
              return raw;
            })()}
          </p>
        </div>
        {dataset.activated_at && (
          <div>
            <p className="text-gray-400">Activated At</p>
            <p className="text-white">{new Date(dataset.activated_at).toLocaleDateString()}</p>
          </div>
        )}
        {dataset.archived_at && (
          <div>
            <p className="text-gray-400">Archived At</p>
            <p className="text-white">{new Date(dataset.archived_at).toLocaleDateString()}</p>
          </div>
        )}
      </div>

      {/* Fields table */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-sm font-medium text-gray-300">
            Fields <span className="text-gray-500 ml-1">({dataset.field_count})</span>
          </h2>
          {dataset.last_profiled_at && (
            <span className="text-xs text-gray-500">
              Profiled {new Date(dataset.last_profiled_at).toLocaleString()}
            </span>
          )}
        </div>
        <div data-testid="fields-table">
          {dataset.fields && dataset.fields.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">#</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Name</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Type</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Nullable</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Key Candidate</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Nulls</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Distinct</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Min</th>
                  <th className="text-left px-5 py-2 text-gray-400 font-medium">Max</th>
                </tr>
              </thead>
              <tbody>
                {dataset.fields.map((f) => {
                  // F12 — inline null-percentage bar. If we can compute it
                  // against a known total (field-level row_count if present
                  // on profile_stats, falling back to dataset.field_count is
                  // wrong; keep it None when totals aren't available).
                  const total =
                    typeof f.profile_stats === 'object' && f.profile_stats
                      ? Number((f.profile_stats as Record<string, unknown>)['row_count'] ?? NaN)
                      : NaN;
                  const nullPct =
                    Number.isFinite(total) && total > 0 && f.null_count != null
                      ? (f.null_count / total) * 100
                      : null;
                  const distinctPct =
                    Number.isFinite(total) && total > 0 && f.distinct_count != null
                      ? (f.distinct_count / total) * 100
                      : null;
                  return (
                    <tr key={f.field_id} className="border-b border-gray-700/50" data-testid={`field-row-${f.field_id}`}>
                      <td className="px-5 py-2 text-gray-500">{f.ordinal_position}</td>
                      <td className="px-5 py-2 text-white font-mono">{f.field_name}</td>
                      <td className="px-5 py-2 text-gray-300">{f.data_type}</td>
                      <td className="px-5 py-2 text-gray-300">{f.nullable ? 'Yes' : 'No'}</td>
                      <td className="px-5 py-2 text-gray-300">{f.is_key_candidate ? 'Yes' : '—'}</td>
                      <td className="px-5 py-2 text-gray-300">
                        <FieldStatBar count={f.null_count} pct={nullPct} tone="null" />
                      </td>
                      <td className="px-5 py-2 text-gray-300">
                        <FieldStatBar count={f.distinct_count} pct={distinctPct} tone="distinct" />
                      </td>
                      <td className="px-5 py-2 text-gray-300">{f.min_value ?? '—'}</td>
                      <td className="px-5 py-2 text-gray-300">{f.max_value ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="px-5 py-6 text-center text-gray-400 text-sm">No fields defined yet.</p>
          )}
        </div>
      </div>

      {/* Data Quality — rules + per-column metrics */}
      <DatasetWorkbench
        workspaceId={workspace_id!}
        datasetId={dataset_id!}
        dataset={dataset}
        canWrite={canWrite}
        isArchived={isArchived}
        searchParams={searchParams}
        setSearchParams={setSearchParams}
      />

      {/* Audit log toggle */}
      <div className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden">
        <button
          data-testid="audit-log-toggle"
          className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium text-gray-300 hover:bg-gray-700/30 transition-colors"
          onClick={() => setShowAuditLog((v) => !v)}
        >
          Audit Log
          {showAuditLog ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {showAuditLog && (
          <div data-testid="audit-log-panel" className="px-5 pb-4">
            {auditLoading && <p className="text-gray-400 text-sm py-2">Loading…</p>}
            {auditData?.items?.length === 0 && (
              <p className="text-gray-400 text-sm py-2">No audit events.</p>
            )}
            {auditData?.items?.map((entry: any) => (
              <AuditLogRow key={entry.log_id} entry={entry} />
            ))}
          </div>
        )}
      </div>

      {/* Archive confirmation modal */}
      {showArchiveModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" data-testid="archive-modal">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 max-w-sm w-full mx-4 space-y-4">
            <h3 className="text-white font-semibold">Archive dataset?</h3>
            <p className="text-gray-400 text-sm">
              Archiving <strong>{dataset.dataset_name}</strong> is irreversible. Fields cannot be modified afterwards.
            </p>
            <div className="flex gap-3 pt-2">
              <button
                data-testid="archive-confirm-btn"
                onClick={() => archiveMutation.mutate()}
                disabled={archiveMutation.isPending}
                className="flex-1 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-500 disabled:opacity-50"
              >
                {archiveMutation.isPending ? 'Archiving…' : 'Archive'}
              </button>
              <button
                onClick={() => setShowArchiveModal(false)}
                className="flex-1 py-2 rounded-lg border border-gray-600 text-gray-300 text-sm hover:bg-gray-700"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── F8 — Audit log row with expandable detail ───────────────────────────────
interface AuditEntry {
  log_id: string;
  action_type: string;
  actor_id?: string | null;
  actor_role?: string | null;
  new_data?: Record<string, unknown> | null;
  occurred_at: string | null;
}

function AuditLogRow({ entry }: { entry: AuditEntry }) {
  const [open, setOpen] = useState(false);
  const hasDetail =
    entry.new_data && typeof entry.new_data === 'object' && Object.keys(entry.new_data).length > 0;
  const when = entry.occurred_at ? new Date(entry.occurred_at) : null;
  return (
    <div className="border-b border-gray-700/50 text-sm" data-testid={`audit-row-${entry.log_id}`}>
      <button
        type="button"
        onClick={() => hasDetail && setOpen((v) => !v)}
        className={`w-full flex items-center gap-3 py-2 text-left ${hasDetail ? 'cursor-pointer hover:bg-gray-700/20' : 'cursor-default'}`}
      >
        <span className="text-gray-400 text-xs whitespace-nowrap min-w-[140px]">
          {when ? when.toLocaleString() : '—'}
        </span>
        <span className="text-purple-400 font-mono text-xs">{entry.action_type}</span>
        {entry.actor_role && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border border-gray-600 text-gray-300">
            {entry.actor_role}
          </span>
        )}
        {entry.actor_id && (
          <span className="text-gray-500 text-[11px] font-mono truncate" title={entry.actor_id}>
            {entry.actor_id.slice(0, 8)}…
          </span>
        )}
        {hasDetail && (
          <span className="ml-auto text-gray-500">
            {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </span>
        )}
      </button>
      {open && hasDetail && (
        <pre
          data-testid={`audit-detail-${entry.log_id}`}
          className="mt-1 mb-3 mx-1 p-3 rounded bg-gray-900/70 border border-gray-700 text-[11px] text-gray-200 font-mono whitespace-pre-wrap break-words max-h-64 overflow-y-auto"
        >
          {JSON.stringify(entry.new_data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ── F5 — Tabbed workbench: Sample / Profile / Quality / Lineage ─────────────

type WorkbenchTab = 'sample' | 'profile' | 'quality' | 'lineage';
const VALID_TABS: WorkbenchTab[] = ['sample', 'profile', 'quality', 'lineage'];

interface WorkbenchProps {
  workspaceId: string;
  datasetId: string;
  dataset: Dataset;
  canWrite: boolean;
  isArchived: boolean;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
}

function DatasetWorkbench({
  workspaceId,
  datasetId,
  dataset,
  canWrite,
  isArchived,
  searchParams,
  setSearchParams,
}: WorkbenchProps) {
  const urlTab = searchParams.get('tab') as WorkbenchTab | null;
  const activeTab: WorkbenchTab =
    urlTab && VALID_TABS.includes(urlTab) ? urlTab : 'sample';

  const setTab = (t: WorkbenchTab) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', t);
    setSearchParams(next, { replace: true });
  };

  const tabs: { id: WorkbenchTab; label: string; icon: typeof Eye }[] = [
    { id: 'sample', label: 'Sample', icon: Eye },
    { id: 'profile', label: 'Profile', icon: BarChart3Icon },
    { id: 'quality', label: 'Quality', icon: ShieldCheck },
    { id: 'lineage', label: 'Lineage', icon: Network },
  ];

  return (
    <div
      className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden"
      data-testid="dataset-workbench"
    >
      <div className="border-b border-gray-700 px-2 flex gap-1" role="tablist">
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = t.id === activeTab;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              data-testid={`workbench-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-sm border-b-2 transition-colors ${
                isActive
                  ? 'border-purple-500 text-white'
                  : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="p-0">
        {/* Mount panels lazily by activeTab to avoid kicking off all queries
            up-front; each child component manages its own React Query state. */}
        {activeTab === 'sample' && (
          <DatasetPreviewPanel workspaceId={workspaceId} datasetId={datasetId} />
        )}
        {activeTab === 'profile' && (
          <DatasetProfilingPanel
            workspaceId={workspaceId}
            datasetId={datasetId}
            autoRunOnMount={canWrite && !dataset.last_profiled_at && !isArchived}
          />
        )}
        {activeTab === 'quality' && (
          <DatasetQualityPanel workspaceId={workspaceId} dataset={dataset} />
        )}
        {activeTab === 'lineage' && (
          <LineagePanel workspaceId={workspaceId} dataset={dataset} />
        )}
      </div>
    </div>
  );
}

// ── F11 — Schema drift / freshness badge ───────────────────────────────────
function SchemaDriftBadge({ dataset }: { dataset: Dataset }) {
  const profiledAt = dataset.last_profiled_at ? Date.parse(dataset.last_profiled_at) : NaN;
  if (!Number.isFinite(profiledAt)) {
    return (
      <span
        data-testid="schema-drift-badge"
        title="This dataset has never been profiled. Run a profile to capture column-level statistics and detect drift."
        className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border border-yellow-500/40 bg-yellow-500/10 text-yellow-300"
      >
        Schema not profiled
      </span>
    );
  }
  const ageMs = Date.now() - profiledAt;
  const ageDays = Math.floor(ageMs / 86_400_000);
  if (ageDays >= 7) {
    return (
      <span
        data-testid="schema-drift-badge"
        title={`Last profiled ${ageDays} days ago. Re-profile to refresh statistics and detect drift.`}
        className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border border-orange-500/40 bg-orange-500/10 text-orange-300"
      >
        Stale ({ageDays}d)
      </span>
    );
  }
  return (
    <span
      data-testid="schema-drift-badge"
      title={`Last profiled ${ageDays === 0 ? 'today' : `${ageDays} day${ageDays === 1 ? '' : 's'} ago`}.`}
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    >
      Schema fresh
    </span>
  );
}

// ── F12 — Tiny inline bar for null %/distinct % cells ──────────────────────
function FieldStatBar({
  count,
  pct,
  tone,
}: {
  count: number | null | undefined;
  pct: number | null;
  tone: 'null' | 'distinct';
}) {
  if (count == null) return <span className="text-gray-500">—</span>;
  // For nulls: red→yellow→green as pct grows.
  // For distinct: just neutral teal — high cardinality is informational.
  const color =
    tone === 'null'
      ? pct == null
        ? '#6b7280'
        : pct > 50
          ? '#f87171'
          : pct > 10
            ? '#fbbf24'
            : '#34d399'
      : '#22d3ee';
  const widthPct = pct == null ? 0 : Math.max(2, Math.min(100, pct));
  return (
    <div className="inline-flex items-center gap-2" data-testid={`field-stat-${tone}`}>
      <span className="font-mono text-xs text-gray-300 min-w-[60px] text-right">
        {count.toLocaleString()}
      </span>
      {pct != null && (
        <>
          <div className="w-16 h-1.5 rounded-full bg-gray-700 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${widthPct}%`, background: color }} />
          </div>
          <span className="text-[11px] text-gray-500 min-w-[36px]">
            {pct.toFixed(1)}%
          </span>
        </>
      )}
    </div>
  );
}

// ── F13 — Lineage panel: upstream source + downstream rules/flows ─────────
function LineagePanel({ workspaceId, dataset }: { workspaceId: string; dataset: Dataset }) {
  const { wsPath } = useTenantScopedPath();
  const rulesQuery = useQuery({
    queryKey: ['dataset-lineage-rules', workspaceId, dataset.physical_identifier],
    queryFn: () => listRules(workspaceId, { limit: 1000 }),
    enabled: !!workspaceId && !!dataset.physical_identifier,
    staleTime: 30_000,
  });

  const downstream: RuleResponse[] = (rulesQuery.data ?? []).filter((r) => {
    if (dataset.data_source_id && r.data_source_id) {
      if (r.data_source_id !== dataset.data_source_id) return false;
    }
    const rt = (r.target_table ?? '').toLowerCase();
    const tgt = (dataset.physical_identifier ?? '').toLowerCase();
    if (!rt || !tgt) return false;
    return rt === tgt || rt.endsWith(`.${tgt}`);
  });

  return (
    <div className="px-5 py-5 space-y-5" data-testid="dataset-lineage-panel">
      {/* Upstream */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-2">Upstream source</h3>
        <div
          className="rounded-lg border border-gray-700 bg-gray-900/40 px-4 py-3"
          data-testid="lineage-upstream"
        >
          {dataset.data_source_id ? (
            <Link
              to={wsPath(workspaceId, `/connections/${dataset.data_source_id}`)}
              className="text-sm text-purple-300 hover:text-purple-200"
            >
              {dataset.data_source_name ?? 'Data source'} →
            </Link>
          ) : (
            <p className="text-sm text-gray-400">No connected data source.</p>
          )}
          {dataset.physical_identifier && (
            <p className="mt-1 text-[11px] text-gray-500 font-mono">
              {dataset.schema_name ? `${dataset.schema_name}.` : ''}
              {dataset.physical_identifier}
            </p>
          )}
        </div>
      </section>

      {/* This dataset */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-2">This dataset</h3>
        <div className="rounded-lg border border-purple-500/40 bg-purple-500/10 px-4 py-3">
          <p className="text-sm font-medium text-white">{dataset.dataset_name}</p>
          <p className="text-[11px] text-gray-400">
            {dataset.field_count} field{dataset.field_count === 1 ? '' : 's'} · {dataset.dataset_type}
          </p>
        </div>
      </section>

      {/* Downstream rules */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wide text-gray-400 mb-2">
          Downstream rules{' '}
          <span className="text-gray-500">({downstream.length})</span>
        </h3>
        {rulesQuery.isLoading && (
          <p className="text-xs text-gray-500">Loading rules…</p>
        )}
        {!rulesQuery.isLoading && downstream.length === 0 && (
          <p
            className="text-xs text-gray-500"
            data-testid="lineage-downstream-empty"
          >
            No rules currently target this dataset.
          </p>
        )}
        {downstream.length > 0 && (
          <ul className="space-y-1.5" data-testid="lineage-downstream-list">
            {downstream.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-gray-700 bg-gray-900/40 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    to={wsPath(workspaceId, `/rules?rule=${r.id}`)}
                    className="text-sm text-white hover:text-purple-300 truncate"
                  >
                    {r.name}
                  </Link>
                  {(r.target_columns?.length ?? 0) > 0 && (
                    <p className="text-[11px] text-gray-500 font-mono truncate">
                      {r.target_columns!.join(', ')}
                    </p>
                  )}
                </div>
                <span className="text-[11px] text-gray-400 capitalize whitespace-nowrap">
                  {r.category}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

