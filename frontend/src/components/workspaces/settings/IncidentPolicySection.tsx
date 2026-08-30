/**
 * IncidentPolicySection — D1: workspace-level auto-incident policy editor.
 *
 * Toggles whether F039 auto-creates an Incident from new Issues that match
 * a configurable severity floor + recurrence threshold.
 */
import { useState, useEffect } from 'react';
import { ShieldAlert, Save } from 'lucide-react';

import type { IncidentPolicy, IncidentSeverityFloor } from '../../../types/workspaceSettings';

interface Props {
  value: IncidentPolicy | null;
  canEdit: boolean;
  onSave: (update: IncidentPolicy) => Promise<void>;
}

const SEVERITY_OPTIONS: { value: IncidentSeverityFloor; label: string }[] = [
  { value: 'critical', label: 'Critical only' },
  { value: 'major', label: 'Major and above' },
  { value: 'minor', label: 'Minor and above' },
  { value: 'informational', label: 'All issues' },
];

const PRIORITY_OPTIONS = [
  { value: '', label: 'Derive from severity' },
  { value: 'P1', label: 'P1 — Critical' },
  { value: 'P2', label: 'P2 — High' },
  { value: 'P3', label: 'P3 — Medium' },
  { value: 'P4', label: 'P4 — Low' },
];

const DEFAULT_POLICY: IncidentPolicy = {
  enabled: true,
  min_severity: 'major',
  recurrence_threshold: 1,
  auto_priority: null,
  auto_owner_user_id: null,
};

export default function IncidentPolicySection({ value, canEdit, onSave }: Props) {
  const initial = value ?? DEFAULT_POLICY;
  const [enabled, setEnabled] = useState(initial.enabled);
  const [minSeverity, setMinSeverity] = useState<IncidentSeverityFloor>(initial.min_severity);
  const [recurrence, setRecurrence] = useState<number>(initial.recurrence_threshold);
  const [autoPriority, setAutoPriority] = useState<string>(initial.auto_priority ?? '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (value) {
      setEnabled(value.enabled);
      setMinSeverity(value.min_severity);
      setRecurrence(value.recurrence_threshold);
      setAutoPriority(value.auto_priority ?? '');
    }
  }, [value]);

  const dirty =
    enabled !== initial.enabled ||
    minSeverity !== initial.min_severity ||
    recurrence !== initial.recurrence_threshold ||
    (autoPriority || null) !== (initial.auto_priority ?? null);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({
        enabled,
        min_severity: minSeverity,
        recurrence_threshold: recurrence,
        auto_priority: (autoPriority || null) as IncidentPolicy['auto_priority'],
        auto_owner_user_id: initial.auto_owner_user_id,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-2xl border border-dark-700 bg-dark-800/40 p-6">
      <header className="flex items-start gap-3 mb-4">
        <ShieldAlert className="w-5 h-5 text-amber-400 mt-0.5" />
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-white">Auto-Incident Policy</h2>
          <p className="text-sm text-gray-400 mt-1">
            When enabled, the platform automatically opens an Incident for new Issues that meet
            the severity and recurrence thresholds below. This is on by default to keep critical
            data-quality regressions from going unnoticed.
          </p>
        </div>
      </header>

      <div className="space-y-4">
        {/* Enabled toggle */}
        <label className="flex items-center justify-between gap-3 p-3 rounded-lg border border-dark-700">
          <div>
            <div className="text-sm font-medium text-gray-100">Enable auto-incident creation</div>
            <div className="text-xs text-gray-500">Required for SLA timers and incident dashboards.</div>
          </div>
          <input
            type="checkbox"
            checked={enabled}
            disabled={!canEdit || saving}
            onChange={e => setEnabled(e.target.checked)}
            className="w-5 h-5 accent-amber-500"
          />
        </label>

        {/* Severity floor */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Minimum severity</label>
          <select
            value={minSeverity}
            disabled={!canEdit || saving || !enabled}
            onChange={e => setMinSeverity(e.target.value as IncidentSeverityFloor)}
            className="w-full bg-dark-900 border border-dark-700 rounded-md px-3 py-2 text-sm text-gray-100 disabled:opacity-50"
          >
            {SEVERITY_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Recurrence */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">
            Recurrence threshold (failure_count)
          </label>
          <input
            type="number"
            min={1}
            max={100}
            value={recurrence}
            disabled={!canEdit || saving || !enabled}
            onChange={e => setRecurrence(Math.max(1, parseInt(e.target.value, 10) || 1))}
            className="w-32 bg-dark-900 border border-dark-700 rounded-md px-3 py-2 text-sm text-gray-100 disabled:opacity-50"
          />
          <p className="text-xs text-gray-500 mt-1">
            Open an incident only after the issue has failed this many times.
          </p>
        </div>

        {/* Priority override */}
        <div>
          <label className="block text-sm text-gray-300 mb-1">Default priority</label>
          <select
            value={autoPriority}
            disabled={!canEdit || saving || !enabled}
            onChange={e => setAutoPriority(e.target.value)}
            className="w-full bg-dark-900 border border-dark-700 rounded-md px-3 py-2 text-sm text-gray-100 disabled:opacity-50"
          >
            {PRIORITY_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {canEdit && (
          <div className="flex justify-end pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={!dirty || saving}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-2 text-sm font-medium text-white transition-colors"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving…' : 'Save policy'}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
