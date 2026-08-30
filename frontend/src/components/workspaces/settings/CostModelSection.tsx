/**
 * CostModelSection — configure USD cost per issue severity for KQI-066 (Estimated Cost Saved).
 *
 * Read-only for data_engineer and data_steward (canEdit=false).
 * Editable only for workspace_administrator (canEdit=true).
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { getCostModel, updateCostModel, type CostModelEntry } from '../../../services/kqiService';

const SEVERITIES: { key: string; label: string; color: string }[] = [
  { key: 'critical', label: 'Critical', color: 'text-red-400' },
  { key: 'major',    label: 'Major',    color: 'text-orange-400' },
  { key: 'minor',    label: 'Minor',    color: 'text-yellow-400' },
  { key: 'info',     label: 'Info',     color: 'text-blue-400' },
];

interface Props {
  workspaceId: string;
  canEdit: boolean;
}

const QUERY_KEY = (wsId: string) => ['cost-model', wsId];

export default function CostModelSection({ workspaceId, canEdit }: Props) {
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEY(workspaceId),
    queryFn: () => getCostModel(workspaceId),
    staleTime: 60_000,
  });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const costMap: Record<string, number> = {};
  if (data) {
    for (const e of data.costs) costMap[e.severity] = e.estimated_cost_usd;
  }

  const handleEdit = () => {
    setDraft({ ...costMap });
    setError(null);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setError(null);
  };

  const handleSave = async () => {
    for (const { key } of SEVERITIES) {
      const v = draft[key];
      if (v === undefined || v <= 0 || isNaN(v)) {
        setError(`${key.charAt(0).toUpperCase() + key.slice(1)} cost must be a positive number.`);
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      const costs: CostModelEntry[] = SEVERITIES.map(({ key }) => ({
        severity: key,
        estimated_cost_usd: draft[key],
      }));
      await updateCostModel(workspaceId, costs);
      await queryClient.invalidateQueries({ queryKey: QUERY_KEY(workspaceId) });
      toast.success('Cost model updated.');
      setEditing(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save cost model.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="cost-model-section"
    >
      <div className="flex items-center justify-between mb-1">
        <div>
          <h2 className="text-lg font-semibold text-white">Estimated Cost Model</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            USD cost per issue by severity — used to calculate{' '}
            <span className="text-gray-400">Estimated Cost Saved (KQI-066)</span>.
            {data && !data.is_custom && (
              <span className="ml-1 text-indigo-400">(using system defaults)</span>
            )}
          </p>
        </div>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            data-testid="cost-model-edit-btn"
          >
            Edit
          </button>
        )}
      </div>

      {isLoading && (
        <div className="mt-4 space-y-2 animate-pulse">
          {SEVERITIES.map(({ key }) => (
            <div key={key} className="h-8 rounded-lg bg-dark-700" />
          ))}
        </div>
      )}

      {isError && (
        <p className="mt-4 text-sm text-red-400">Failed to load cost model.</p>
      )}

      {!isLoading && !isError && !editing && (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
          {SEVERITIES.map(({ key, label, color }) => (
            <div
              key={key}
              className="rounded-xl bg-dark-900 border border-dark-700 p-3 text-center"
              data-testid={`cost-model-display-${key}`}
            >
              <p className={`text-xs font-medium uppercase tracking-wide ${color} mb-1`}>{label}</p>
              <p className="text-lg font-bold text-white">
                ${(costMap[key] ?? 0).toLocaleString()}
              </p>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <div className="mt-4 space-y-3">
          {SEVERITIES.map(({ key, label, color }) => (
            <label key={key} className="block">
              <span className={`text-sm font-medium mb-1 block ${color}`}>{label} — USD per issue</span>
              <input
                type="number"
                min={1}
                step={100}
                value={draft[key] ?? ''}
                onChange={(e) =>
                  setDraft((prev) => ({ ...prev, [key]: parseFloat(e.target.value) }))
                }
                className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
                data-testid={`cost-model-input-${key}`}
              />
            </label>
          ))}

          {error && (
            <p className="text-sm text-red-400" data-testid="cost-model-error">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              data-testid="cost-model-save-btn"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-4 py-2 rounded-lg border border-dark-600 hover:bg-dark-700 text-gray-300 text-sm transition-colors"
              data-testid="cost-model-cancel-btn"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
