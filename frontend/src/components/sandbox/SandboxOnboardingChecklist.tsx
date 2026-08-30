/**
 * F134 P12 — SandboxOnboardingChecklist
 *
 * Shows the guided onboarding steps for sandbox users.
 * Can be embedded on the workspace overview page.
 */
import React, { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import {
  completeSandboxStep,
  getSandboxOnboarding,
  type OnboardingStep,
} from '../../services/sandboxUserService';

const STEP_LABELS: Record<string, string> = {
  view_dataset: 'Explore a dataset',
  view_rule: 'View an existing rule',
  run_check: 'Run your first DQ check',
  open_issue: 'Open a data quality issue',
  view_dashboard: 'Visit the dashboard',
  create_rule: 'Create a new rule',
};

export default function SandboxOnboardingChecklist() {
  const [steps, setSteps] = useState<OnboardingStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [allComplete, setAllComplete] = useState(false);
  const [completing, setCompleting] = useState<string | null>(null);

  const load = async () => {
    try {
      const resp = await getSandboxOnboarding();
      setSteps(resp.steps);
      setAllComplete(resp.all_complete);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleComplete = async (stepId: string) => {
    setCompleting(stepId);
    try {
      await completeSandboxStep(stepId);
      await load();
    } finally {
      setCompleting(null);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-6">
        <Loader2 className="w-5 h-5 animate-spin text-primary-400" />
      </div>
    );
  }

  return (
    <div className="card p-4 space-y-3" data-testid="sandbox-onboarding">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Getting started</h3>
        {allComplete && (
          <span className="text-xs text-green-400 font-medium">All done! 🎉</span>
        )}
      </div>
      <div className="space-y-2">
        {steps.map((step) => (
          <div
            key={step.step_id}
            className={`flex items-center justify-between p-2 rounded-lg ${
              step.completed ? 'bg-gray-800/40' : 'bg-gray-800/70'
            }`}
          >
            <div className="flex items-center space-x-2">
              {step.completed ? (
                <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
              ) : (
                <Circle className="w-4 h-4 text-gray-600 shrink-0" />
              )}
              <span
                className={`text-sm ${
                  step.completed ? 'line-through text-gray-500' : 'text-gray-300'
                }`}
              >
                {STEP_LABELS[step.step_id] ?? step.step_id}
              </span>
            </div>
            {!step.completed && (
              <button
                onClick={() => handleComplete(step.step_id)}
                disabled={completing === step.step_id}
                className="text-xs px-2 py-0.5 rounded bg-primary-700/50 hover:bg-primary-700 text-primary-300 transition-colors disabled:opacity-50"
              >
                {completing === step.step_id ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  'Mark done'
                )}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
