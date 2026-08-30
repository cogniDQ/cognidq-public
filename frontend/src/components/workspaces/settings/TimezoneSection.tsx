/**
 * TimezoneSection — displays and allows editing the workspace default timezone.
 *
 * Edit control visible only to workspace_administrator role.
 * Uses a free-text input with client-side IANA format hint.
 */
import { useState } from 'react';
import type { TimezonePolicy } from '../../../types/workspaceSettings';

interface Props {
  value: TimezonePolicy;
  canEdit: boolean;
  onSave: (update: TimezonePolicy) => Promise<void>;
}

// These are the most common IANA timezone values offered in the select.
const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Moscow',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Australia/Sydney',
  'Pacific/Auckland',
];

export default function TimezoneSection({ value, canEdit, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value.default_timezone);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleEdit = () => {
    setDraft(value.default_timezone);
    setError(null);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setError(null);
  };

  const handleSave = async () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setError('Timezone is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ default_timezone: trimmed });
      setEditing(false);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to save timezone.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="timezone-section"
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Timezone</h2>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            data-testid="timezone-edit-btn"
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">Default Timezone (IANA)</span>
            <select
              value={COMMON_TIMEZONES.includes(draft) ? draft : ''}
              onChange={(e) => {
                if (e.target.value) setDraft(e.target.value);
              }}
              className="w-full rounded-lg border border-dark-600 bg-dark-700 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
              data-testid="timezone-select"
            >
              <option value="">— or type below —</option>
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">Or enter any IANA timezone</span>
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. America/New_York"
              className="w-full rounded-lg border border-dark-600 bg-dark-700 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
              data-testid="timezone-input"
            />
          </label>

          {error && (
            <p className="text-sm text-red-400" data-testid="timezone-error" role="alert">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg border border-dark-600 text-gray-400 hover:text-white text-sm transition-colors"
              data-testid="timezone-cancel-btn"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              data-testid="timezone-save-btn"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-white font-mono" data-testid="timezone-value">
          {value.default_timezone}
        </p>
      )}
    </section>
  );
}
