/**
 * IssueGroupingSection — displays and allows editing the issue grouping mode.
 *
 * Uses a radio group for the three valid modes.
 * Edit control visible only to workspace_administrator role.
 */
import { useState } from 'react';
import type { IssueGroupingMode } from '../../../types/workspaceSettings';

interface Props {
  value: IssueGroupingMode;
  canEdit: boolean;
  onSave: (mode: IssueGroupingMode) => Promise<void>;
}

const MODES: { value: IssueGroupingMode; label: string; description: string }[] = [
  {
    value: 'one_per_execution',
    label: 'One per execution',
    description: 'A single issue is created per flow execution.',
  },
  {
    value: 'one_per_rule',
    label: 'One per rule',
    description: 'One issue per rule that triggers during the execution.',
  },
  {
    value: 'one_per_day',
    label: 'One per day',
    description: 'Issues are grouped into one per day across all rules.',
  },
];

const MODE_LABELS: Record<IssueGroupingMode, string> = {
  one_per_execution: 'One per execution',
  one_per_rule: 'One per rule',
  one_per_day: 'One per day',
};

export default function IssueGroupingSection({ value, canEdit, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<IssueGroupingMode>(value);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleEdit = () => {
    setDraft(value);
    setError(null);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      setEditing(false);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to save issue grouping mode.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="issue-grouping-section"
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Issue Grouping</h2>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            data-testid="grouping-edit-btn"
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <fieldset>
            <legend className="sr-only">Issue grouping mode</legend>
            <div className="space-y-2">
              {MODES.map((mode) => (
                <label
                  key={mode.value}
                  className="flex items-start gap-3 cursor-pointer"
                  data-testid={`grouping-option-${mode.value}`}
                >
                  <input
                    type="radio"
                    name="issue_grouping_mode"
                    value={mode.value}
                    checked={draft === mode.value}
                    onChange={() => setDraft(mode.value)}
                    className="mt-0.5 accent-indigo-500"
                    data-testid={`grouping-radio-${mode.value}`}
                  />
                  <span>
                    <span className="text-sm font-medium text-white">{mode.label}</span>
                    <span className="block text-xs text-gray-400">{mode.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {error && (
            <p className="text-sm text-red-400" data-testid="grouping-error" role="alert">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg border border-dark-600 text-gray-400 hover:text-white text-sm transition-colors"
              data-testid="grouping-cancel-btn"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              data-testid="grouping-save-btn"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-white" data-testid="grouping-value">
          {MODE_LABELS[value]}
        </p>
      )}
    </section>
  );
}
