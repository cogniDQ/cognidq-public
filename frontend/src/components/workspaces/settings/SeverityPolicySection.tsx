/**
 * SeverityPolicySection — displays and allows editing the four severity labels.
 *
 * Edit control visible only to workspace_administrator role.
 */
import { useState } from 'react';
import type { SeverityPolicy } from '../../../types/workspaceSettings';

interface Props {
  value: SeverityPolicy;
  canEdit: boolean;
  onSave: (update: SeverityPolicy) => Promise<void>;
}

export default function SeverityPolicySection({ value, canEdit, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SeverityPolicy>({ ...value });
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
    for (const [key, val] of Object.entries(draft)) {
      if (!val.trim()) {
        setError(`${key.replace('_label', '')} label cannot be empty.`);
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      setEditing(false);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to save severity policy.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const FIELDS: { key: keyof SeverityPolicy; label: string; testid: string }[] = [
    { key: 'critical_label', label: 'Critical', testid: 'severity-critical-input' },
    { key: 'major_label', label: 'Major', testid: 'severity-major-input' },
    { key: 'minor_label', label: 'Minor', testid: 'severity-minor-input' },
    { key: 'informational_label', label: 'Informational', testid: 'severity-informational-input' },
  ];

  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="severity-policy-section"
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Severity Labels</h2>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            data-testid="severity-edit-btn"
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          {FIELDS.map(({ key, label, testid }) => (
            <label key={key} className="block">
              <span className="text-sm text-gray-400 mb-1 block">{label}</span>
              <input
                type="text"
                value={draft[key]}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                className="w-full rounded-lg border border-dark-600 bg-dark-700 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
                data-testid={testid}
              />
            </label>
          ))}

          {error && (
            <p className="text-sm text-red-400" data-testid="severity-error" role="alert">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg border border-dark-600 text-gray-400 hover:text-white text-sm transition-colors"
              data-testid="severity-cancel-btn"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              data-testid="severity-save-btn"
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
              <dd className="text-white mt-0.5" data-testid={`severity-${key.replace('_label', '')}-value`}>
                {value[key]}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
