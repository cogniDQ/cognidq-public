import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  Circle,
  Database,
  BookOpen,
  Sparkles,
  ArrowRight,
  Loader2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import {
  getSandboxOnboarding,
  type OnboardingStep,
} from '../services/sandboxUserService';

interface WizardStep {
  id: string;
  matches: string[];
  title: string;
  description: string;
  icon: LucideIcon;
  cta: { label: string; to: string };
}

const STEPS: WizardStep[] = [
  {
    id: 'connect',
    matches: ['connect_source', 'add_connection', 'connection'],
    title: 'Connect a data source',
    description:
      'Bring in a Postgres, Snowflake, BigQuery, or file source. Read-only by default — we only fetch metadata and the rows your rules need.',
    icon: Database,
    cta: { label: 'Add connection', to: '/hub' },
  },
  {
    id: 'glossary',
    matches: ['import_glossary', 'glossary', 'business_glossary'],
    title: 'Import a business glossary',
    description:
      'A glossary teaches CogniDQ your terms. The NL rule builder uses it to disambiguate "customer", "order", and "active".',
    icon: BookOpen,
    cta: { label: 'Open glossary', to: '/hub' },
  },
  {
    id: 'rule',
    matches: ['first_rule', 'create_rule', 'rule'],
    title: 'Write your first rule',
    description:
      'Type a sentence like "every order must have a valid customer". We will generate the check, the SQL, and the expected outcome.',
    icon: Sparkles,
    cta: { label: 'Open rule builder', to: '/hub' },
  },
];

function matchStep(wizard: WizardStep, api: OnboardingStep[]): OnboardingStep | undefined {
  return api.find((s) => wizard.matches.some((m) => s.step_id.toLowerCase().includes(m)));
}

export default function OnboardingWizardPage() {
  const [apiSteps, setApiSteps] = useState<OnboardingStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const resp = await getSandboxOnboarding();
        if (alive) setApiSteps(resp.steps);
      } catch {
        if (alive) setError('Onboarding progress is unavailable. You can still follow the steps below.');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const completed = STEPS.filter((s) => matchStep(s, apiSteps)?.completed).length;
  const percent = Math.round((completed / STEPS.length) * 100);

  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <p className="text-xs font-semibold uppercase tracking-widest text-brand">Get started</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight text-content">
        Your first three steps with CogniDQ
      </h1>
      <p className="mt-3 text-base text-content-muted">
        Finish the checklist below to publish a working quality rule against your data.
      </p>

      <div className="mt-6">
        <div className="flex items-center justify-between text-sm">
          <span className="text-content-muted">
            {completed} of {STEPS.length} complete
          </span>
          <span className="font-semibold text-content">{percent}%</span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-raised">
          <div
            className="h-full rounded-full bg-brand transition-all"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {error ? (
        <div className="mt-4 rounded-lg border border-warning/40 bg-warning-soft p-3 text-sm text-warning">
          {error}
        </div>
      ) : null}

      <ol className="mt-8 space-y-4">
        {STEPS.map((step, idx) => {
          const apiState = matchStep(step, apiSteps);
          const isDone = !!apiState?.completed;
          const Icon = step.icon;
          return (
            <li
              key={step.id}
              className={`rounded-xl border p-6 transition-colors ${
                isDone ? 'border-success/40 bg-success-soft' : 'border-edge bg-surface-raised'
              }`}
            >
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0">
                  {loading ? (
                    <Loader2 className="h-6 w-6 animate-spin text-content-muted" />
                  ) : isDone ? (
                    <CheckCircle2 className="h-6 w-6 text-success" />
                  ) : (
                    <Circle className="h-6 w-6 text-content-subtle" />
                  )}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-brand" />
                    <span className="text-xs font-semibold uppercase tracking-widest text-brand">
                      Step {idx + 1}
                    </span>
                  </div>
                  <h2 className="mt-1 text-lg font-semibold text-content">{step.title}</h2>
                  <p className="mt-1 text-sm text-content-muted">{step.description}</p>
                  {!isDone ? (
                    <Link
                      to={step.cta.to}
                      className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
                    >
                      {step.cta.label}
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  ) : null}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <div className="mt-10 rounded-xl border border-edge bg-surface-raised p-6 text-sm text-content-muted">
        Stuck?{' '}
        <Link to="/contact" className="font-semibold text-brand hover:underline">
          Talk to us
        </Link>{' '}
        — we'll pair with you to get the first rule live.
      </div>
    </div>
  );
}
