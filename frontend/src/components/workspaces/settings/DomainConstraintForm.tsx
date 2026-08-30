/**
 * DomainConstraintForm — reusable form for dataset or rule naming constraints.
 *
 * Fields: max_length (optional), allowed_pattern (optional regex), forbidden_keywords (optional list).
 */
import { useState } from 'react';
import type { NamingConstraint } from '../../../types/workspaceSettings';

interface Props {
  label: string;
  value: NamingConstraint;
  canEdit: boolean;
  testidPrefix: string;
  onSave: (update: NamingConstraint) => Promise<void>;
}

function isValidRegex(pattern: string): boolean {
  try {
     
    new RegExp(pattern);
    return true;
  } catch {
    return false;
  }
}

export default function DomainConstraintForm({ label, value, canEdit, testidPrefix, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draftMaxLength, setDraftMaxLength] = useState<string>(
    value.max_length !== null ? String(value.max_length) : '',
  );
  const [draftPattern, setDraftPattern] = useState(value.allowed_pattern ?? '');
  const [draftKeywords, setDraftKeywords] = useState(
    value.forbidden_keywords?.join(', ') ?? '',
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleEdit = () => {
    setDraftMaxLength(value.max_length !== null ? String(value.max_length) : '');
    setDraftPattern(value.allowed_pattern ?? '');
    setDraftKeywords(value.forbidden_keywords?.join(', ') ?? '');
    setError(null);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setError(null);
  };

  const handleSave = async () => {
    // Validate regex pattern if provided
    if (draftPattern.trim() && !isValidRegex(draftPattern.trim())) {
      setError('Invalid regular expression pattern.');
      return;
    }

    const maxLengthNum = draftMaxLength.trim()
      ? parseInt(draftMaxLength.trim(), 10)
      : null;

    if (draftMaxLength.trim() && (isNaN(maxLengthNum!) || maxLengthNum! < 1)) {
      setError('Max length must be a positive integer.');
      return;
    }

    const keywords = draftKeywords
      .split(',')
      .map((k) => k.trim())
      .filter((k) => k.length > 0);

    setSaving(true);
    setError(null);
    try {
      await onSave({
        max_length: maxLengthNum,
        allowed_pattern: draftPattern.trim() || null,
        forbidden_keywords: keywords.length > 0 ? keywords : null,
      });
      setEditing(false);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : `Failed to save ${label} naming constraints.`;
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="rounded-xl border border-dark-600 bg-dark-700/40 p-4"
      data-testid={`${testidPrefix}-constraint-form`}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">{label}</h3>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-2.5 py-1 rounded-lg bg-dark-600 hover:bg-dark-500 text-gray-300 text-xs font-medium transition-colors"
            data-testid={`${testidPrefix}-edit-btn`}
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs text-gray-400 mb-1 block">Max length (optional)</span>
            <input
              type="number"
              min={1}
              value={draftMaxLength}
              onChange={(e) => setDraftMaxLength(e.target.value)}
              placeholder="No limit"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-white text-sm focus:border-indigo-500 focus:outline-none"
              data-testid={`${testidPrefix}-max-length-input`}
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400 mb-1 block">Allowed pattern (regex, optional)</span>
            <input
              type="text"
              value={draftPattern}
              onChange={(e) => {
                setDraftPattern(e.target.value);
                setError(null);
              }}
              placeholder="e.g. ^[a-z][a-z0-9_]*$"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-white text-sm font-mono focus:border-indigo-500 focus:outline-none"
              data-testid={`${testidPrefix}-pattern-input`}
            />
          </label>

          <label className="block">
            <span className="text-xs text-gray-400 mb-1 block">Forbidden keywords (comma-separated, optional)</span>
            <input
              type="text"
              value={draftKeywords}
              onChange={(e) => setDraftKeywords(e.target.value)}
              placeholder="e.g. temp, draft, test"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-white text-sm focus:border-indigo-500 focus:outline-none"
              data-testid={`${testidPrefix}-keywords-input`}
            />
          </label>

          {error && (
            <p className="text-xs text-red-400" data-testid={`${testidPrefix}-error`} role="alert">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-2.5 py-1 rounded-lg border border-dark-600 text-gray-400 hover:text-white text-xs transition-colors"
              data-testid={`${testidPrefix}-cancel-btn`}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
              data-testid={`${testidPrefix}-save-btn`}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      ) : (
        <dl className="space-y-1.5 text-sm">
          <div>
            <dt className="text-xs text-gray-500">Max length</dt>
            <dd className="text-white" data-testid={`${testidPrefix}-max-length-value`}>
              {value.max_length !== null ? value.max_length : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Allowed pattern</dt>
            <dd className="text-white font-mono text-xs" data-testid={`${testidPrefix}-pattern-value`}>
              {value.allowed_pattern ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Forbidden keywords</dt>
            <dd className="text-white" data-testid={`${testidPrefix}-keywords-value`}>
              {value.forbidden_keywords?.length
                ? value.forbidden_keywords.join(', ')
                : '—'}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}
