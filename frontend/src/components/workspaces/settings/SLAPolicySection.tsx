/**
 * SLAPolicySection — displays and allows editing SLA resolution hours per severity.
 *
 * Client-side ordering validation: critical_hours <= major_hours <= minor_hours.
 * Edit control visible only to workspace_administrator role.
 */
import { useState } from 'react';
import type { SlaPolicy } from '../../../types/workspaceSettings';

interface Props {
  value: SlaPolicy;
  canEdit: boolean;
  onSave: (update: SlaPolicy) => Promise<void>;
}

export default function SLAPolicySection({ value, canEdit, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SlaPolicy>({ ...value });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleEdit = () => {
    setDraft({ ...value });
    setError(null);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setError(null);
  };

  const handleSave = async () => {
    // Client-side SLA ordering validation
    const { critical_hours, major_hours, minor_hours } = draft;
    if (critical_hours > major_hours) {
      setError('Critical SLA hours must be ≤ Major SLA hours.');
      return;
    }
    if (major_hours > minor_hours) {
      setError('Major SLA hours must be ≤ Minor SLA hours.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      setEditing(false);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to save SLA policy.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const FIELDS: {
    key: keyof SlaPolicy;
    label: string;
    testid: string;
    nullable?: boolean;
  }[] = [
    { key: 'critical_hours', label: 'Critical (hours)', testid: 'sla-critical-input' },
    { key: 'major_hours', label: 'Major (hours)', testid: 'sla-major-input' },
    { key: 'minor_hours', label: 'Minor (hours)', testid: 'sla-minor-input' },
    { key: 'informational_hours', label: 'Informational (hours, optional)', testid: 'sla-informational-input', nullable: true },
  ];

  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="sla-policy-section"
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">SLA Policy</h2>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            data-testid="sla-edit-btn"
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            Ordering: Critical ≤ Major ≤ Minor (lower = stricter SLA)
          </p>
          {FIELDS.map(({ key, label, testid, nullable }) => (
            <label key={key} className="block">
              <span className="text-sm text-gray-400 mb-1 block">{label}</span>
              <input
                type="number"
                min={1}
                value={draft[key] ?? ''}
                onChange={(e) => {
                  const num = e.target.value === '' ? null : parseInt(e.target.value, 10);
                  setDraft((d) => ({ ...d, [key]: nullable ? num : (num ?? d[key]) }));
                }}
                placeholder={nullable ? 'Leave blank to clear' : ''}
                className="w-full rounded-lg border border-dark-600 bg-dark-700 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
                data-testid={testid}
              />
            </label>
          ))}

          {error && (
            <p className="text-sm text-red-400" data-testid="sla-error" role="alert">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg border border-dark-600 text-gray-400 hover:text-white text-sm transition-colors"
              data-testid="sla-cancel-btn"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              data-testid="sla-save-btn"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <dl className="grid grid-cols-2 gap-3">
          {FIELDS.map(({ key, label }) => (
            <div key={key}>
              <dt className="text-xs text-gray-500 uppercase tracking-wide">{label}</dt>
              <dd className="text-white mt-0.5" data-testid={`sla-${key.replace('_hours', '')}-value`}>
                {value[key] !== null ? `${value[key]}h` : '—'}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
