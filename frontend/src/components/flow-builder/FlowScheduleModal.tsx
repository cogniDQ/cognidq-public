/**
 * F115 — Flow Schedule Management Modal
 */
import React, { useState, useEffect } from 'react';
import { X, Clock, Loader2, Check, AlertCircle } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import flowService from '../../services/flow';

interface FlowScheduleModalProps {
  workspaceId: string;
  flowId: string;
  onClose: () => void;
}

const CRON_PRESETS = [
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Every 6 hours', cron: '0 */6 * * *' },
  { label: 'Daily at 2 AM', cron: '0 2 * * *' },
  { label: 'Daily at 8 AM', cron: '0 8 * * *' },
  { label: 'Weekdays at 6 AM', cron: '0 6 * * 1-5' },
  { label: 'Weekly (Sunday midnight)', cron: '0 0 * * 0' },
  { label: 'Monthly (1st at midnight)', cron: '0 0 1 * *' },
];

export const FlowScheduleModal: React.FC<FlowScheduleModalProps> = ({
  workspaceId,
  flowId,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(false);
  const [cron, setCron] = useState('0 2 * * *');
  const [timezone, setTimezone] = useState('UTC');
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    error?: string;
    next_runs: string[];
  } | null>(null);

  const { data: scheduleData, isLoading } = useQuery({
    queryKey: ['flow-schedule', workspaceId, flowId],
    queryFn: () => flowService.getSchedule(workspaceId, flowId),
  });

  useEffect(() => {
    if (scheduleData?.schedule) {
      setEnabled(scheduleData.schedule.enabled);
      setCron(scheduleData.schedule.cron_expression || scheduleData.schedule.cron || '0 2 * * *');
      setTimezone(scheduleData.schedule.timezone || 'UTC');
    }
  }, [scheduleData]);

  const validateMutation = useMutation({
    mutationFn: () => flowService.validateCron(workspaceId, flowId, { enabled, cron, timezone }),
    onSuccess: (data) => setValidationResult(data),
  });

  const saveMutation = useMutation({
    mutationFn: () => flowService.setSchedule(workspaceId, flowId, { enabled, cron, timezone }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['flow-schedule'] });
      onClose();
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => flowService.removeSchedule(workspaceId, flowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['flow-schedule'] });
      onClose();
    },
  });

  if (isLoading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="bg-gray-800 rounded-xl p-8">
          <Loader2 className="w-6 h-6 animate-spin text-purple-400 mx-auto" />
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-lg mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center space-x-2">
            <Clock className="w-5 h-5 text-purple-400" />
            <h2 className="text-lg font-semibold text-white">Flow Schedule</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {/* Enable toggle */}
          <label className="flex items-center justify-between cursor-pointer">
            <span className="text-sm text-gray-300">Enable Schedule</span>
            <div
              className={`relative w-10 h-5 rounded-full transition-colors ${enabled ? 'bg-purple-500' : 'bg-gray-600'}`}
              onClick={() => setEnabled(!enabled)}
            >
              <div
                className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${enabled ? 'translate-x-5' : 'translate-x-0.5'}`}
              />
            </div>
          </label>

          {/* Presets */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Quick Presets</label>
            <div className="flex flex-wrap gap-1">
              {CRON_PRESETS.map((preset) => (
                <button
                  key={preset.cron}
                  onClick={() => {
                    setCron(preset.cron);
                    setValidationResult(null);
                  }}
                  className={`text-xs px-2 py-1 rounded border transition-colors ${
                    cron === preset.cron
                      ? 'border-purple-500 bg-purple-500/20 text-purple-300'
                      : 'border-gray-600 text-gray-400 hover:border-gray-500'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {/* Cron expression */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Cron Expression</label>
            <div className="flex space-x-2">
              <input
                type="text"
                value={cron}
                onChange={(e) => {
                  setCron(e.target.value);
                  setValidationResult(null);
                }}
                className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-purple-500"
                placeholder="0 2 * * *"
              />
              <button
                onClick={() => validateMutation.mutate()}
                disabled={validateMutation.isPending}
                className="px-3 py-2 text-xs bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded text-gray-300"
              >
                {validateMutation.isPending ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  'Preview'
                )}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">Format: minute hour day month weekday</p>
          </div>

          {/* Timezone */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Timezone</label>
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
            >
              <option value="UTC">UTC</option>
              <option value="US/Eastern">US/Eastern</option>
              <option value="US/Central">US/Central</option>
              <option value="US/Pacific">US/Pacific</option>
              <option value="Europe/London">Europe/London</option>
              <option value="Europe/Berlin">Europe/Berlin</option>
              <option value="Asia/Tokyo">Asia/Tokyo</option>
              <option value="Asia/Shanghai">Asia/Shanghai</option>
            </select>
          </div>

          {/* Validation result */}
          {validationResult && (
            <div
              className={`rounded p-3 text-sm ${
                validationResult.valid
                  ? 'bg-green-500/10 border border-green-500/30'
                  : 'bg-red-500/10 border border-red-500/30'
              }`}
            >
              {validationResult.valid ? (
                <div>
                  <div className="flex items-center space-x-1 text-green-400 mb-2">
                    <Check className="w-4 h-4" />
                    <span>Valid cron expression</span>
                  </div>
                  <div className="text-xs text-gray-400">
                    <p className="mb-1">Next 5 runs:</p>
                    {validationResult.next_runs.map((run, i) => (
                      <p key={i} className="text-gray-300">
                        {new Date(run).toLocaleString()}
                      </p>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex items-center space-x-1 text-red-400">
                  <AlertCircle className="w-4 h-4" />
                  <span>{validationResult.error}</span>
                </div>
              )}
            </div>
          )}

          {/* Current schedule info */}
          {scheduleData?.next_run_at && (
            <div className="bg-gray-700/50 rounded p-3 text-xs text-gray-400">
              Next scheduled run: <span className="text-white">{new Date(scheduleData.next_run_at).toLocaleString()}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-700">
          <button
            onClick={() => removeMutation.mutate()}
            disabled={removeMutation.isPending || !scheduleData?.schedule}
            className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
          >
            Remove Schedule
          </button>
          <div className="flex space-x-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || !cron.trim()}
              className="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-500 text-white rounded disabled:opacity-50"
            >
              {saveMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                'Save Schedule'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
