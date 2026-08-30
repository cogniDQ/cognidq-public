import { Link } from 'react-router-dom';
import {
  Sparkles,
  BookOpen,
  Workflow,
  PlayCircle,
  Gauge,
  Bug,
  FileSearch,
  BellRing,
  ArrowRight,
  ShieldCheck,
  Database,
  Slack,
  Mail,
  Webhook,
  ChevronRight,
  CheckCircle2,
  Zap,
  Lock,
  Activity,
  TrendingUp,
  Quote,
  Star,
  Cloud,
  Server,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

// ─── Section 1: Hero ─────────────────────────────────────────────────────────

function Hero() {
  return (
    <section className="relative overflow-hidden pt-16 pb-24 lg:pt-24 lg:pb-32">
      {/* Decorative gradient orbs */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute left-1/2 top-0 h-[40rem] w-[40rem] -translate-x-1/2 rounded-full bg-gradient-to-br from-brand/20 via-info/10 to-transparent blur-3xl" />
        <div className="absolute right-0 top-40 h-72 w-72 rounded-full bg-info/15 blur-3xl" />
        <div className="absolute left-10 bottom-0 h-64 w-64 rounded-full bg-brand/15 blur-3xl" />
      </div>

      <div className="grid items-center gap-16 lg:grid-cols-[1.05fr_1fr]">
        {/* Left: copy + CTAs */}
        <div className="text-center lg:text-left">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand-soft/50 px-4 py-1.5 text-sm font-medium text-brand backdrop-blur">
            <Sparkles className="h-4 w-4" />
            The AI Trust Layer for Enterprise Data Quality
          </div>
          <h1 className="mt-6 text-5xl font-bold leading-[1.05] tracking-tight text-content lg:text-6xl xl:text-7xl">
            Turn business rules into{' '}
            <span className="bg-gradient-to-r from-brand via-info to-brand bg-clip-text text-transparent">
              executable trust
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-content-muted lg:mx-0">
            CogniDQ understands your data, your rules, and your people — and gives
            every team a shared, auditable view of data quality across the warehouse.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
            <Link
              to="/hub"
              className="group inline-flex items-center gap-2 rounded-lg bg-brand px-6 py-3 text-base font-semibold text-white shadow-lg shadow-brand/30 transition-all hover:bg-brand-hover hover:shadow-xl hover:shadow-brand/40"
            >
              Go to DQ Hub
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              to="/request-demo"
              className="inline-flex items-center gap-2 rounded-lg border border-edge-strong bg-surface-raised px-6 py-3 text-base font-semibold text-content transition-colors hover:border-brand hover:text-brand"
            >
              Request a demo
            </Link>
          </div>

          <ul className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-content-muted lg:justify-start">
            {[
              { icon: ShieldCheck, label: 'Read-only by default' },
              { icon: Lock, label: 'Tenant-isolated' },
              { icon: Activity, label: 'Full audit trail' },
            ].map(({ icon: Icon, label }) => (
              <li key={label} className="inline-flex items-center gap-1.5">
                <Icon className="h-4 w-4 text-success" />
                {label}
              </li>
            ))}
          </ul>
        </div>

        {/* Right: product mockup */}
        <HeroMockup />
      </div>
    </section>
  );
}

function HeroMockup() {
  return (
    <div className="relative mx-auto w-full max-w-xl lg:max-w-none">
      {/* Glow behind */}
      <div className="pointer-events-none absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-brand/30 via-info/20 to-transparent blur-2xl" />

      {/* Browser chrome */}
      <div className="overflow-hidden rounded-2xl border border-edge-strong bg-surface-raised shadow-2xl">
        <div className="flex items-center gap-2 border-b border-edge bg-surface px-4 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-danger/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-warning/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-success/60" />
          <div className="ml-4 inline-flex items-center gap-1.5 rounded-md border border-edge bg-surface-raised px-2.5 py-1 text-xs text-content-muted">
            <Lock className="h-3 w-3" />
            cognidq.app / dashboard
          </div>
        </div>

        <div className="space-y-4 p-6">
          {/* KPI strip */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'DQ Score', value: '94.7', delta: '+2.1', tone: 'success' },
              { label: 'Open issues', value: '12', delta: '-3', tone: 'warning' },
              { label: 'Datasets', value: '128', delta: '+8', tone: 'info' },
            ].map((m) => (
              <div
                key={m.label}
                className="rounded-lg border border-edge bg-surface p-3"
              >
                <p className="text-[10px] font-semibold uppercase tracking-wider text-content-subtle">
                  {m.label}
                </p>
                <p className="mt-1 text-xl font-bold text-content">{m.value}</p>
                <p
                  className={`text-[10px] font-medium ${
                    m.tone === 'success'
                      ? 'text-success'
                      : m.tone === 'warning'
                        ? 'text-warning'
                        : 'text-info'
                  }`}
                >
                  {m.delta} vs last week
                </p>
              </div>
            ))}
          </div>

          {/* Rule card */}
          <div className="rounded-lg border border-edge bg-surface p-4">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand">
                <Sparkles className="h-3 w-3" /> AI-generated rule
              </span>
              <span className="text-[10px] text-content-muted">trust score 0.94</span>
            </div>
            <p className="mt-3 text-sm font-medium text-content">
              "Every EU customer must have a valid VAT number."
            </p>
            <pre className="mt-3 overflow-x-auto rounded bg-surface-overlay p-2 text-[11px] leading-relaxed text-content-muted">
{`SELECT id FROM customers
 WHERE region = 'EU'
   AND (vat_number IS NULL OR LENGTH(vat_number) < 8);`}
            </pre>
          </div>

          {/* Execution bars */}
          <div className="space-y-2">
            {[
              { name: 'customers_eu_vat', pct: 98, tone: 'success' },
              { name: 'orders_amount_positive', pct: 87, tone: 'warning' },
              { name: 'invoices_unique_id', pct: 100, tone: 'success' },
            ].map((row) => (
              <div key={row.name} className="flex items-center gap-3">
                <span className="w-44 truncate text-xs text-content">{row.name}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-overlay">
                  <div
                    className={`h-full rounded-full ${
                      row.tone === 'success' ? 'bg-success' : 'bg-warning'
                    }`}
                    style={{ width: `${row.pct}%` }}
                  />
                </div>
                <span className="w-10 text-right text-xs font-semibold text-content">
                  {row.pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Trust / metrics bar ─────────────────────────────────────────────────────

function MetricsBar() {
  const metrics = [
    { value: '10×', label: 'Faster rule authoring' },
    { value: '94%', label: 'AI parse accuracy' },
    { value: '6', label: 'Native warehouse connectors' },
    { value: '100%', label: 'Audit trail coverage' },
  ];
  return (
    <section className="my-10 rounded-2xl border border-edge bg-surface-raised/60 p-8 backdrop-blur">
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((m) => (
          <div key={m.label} className="text-center">
            <p className="bg-gradient-to-r from-brand to-info bg-clip-text text-4xl font-bold tracking-tight text-transparent">
              {m.value}
            </p>
            <p className="mt-1 text-xs font-medium uppercase tracking-widest text-content-muted">
              {m.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ─── Feature highlights (3-up) ───────────────────────────────────────────────

function FeatureHighlights() {
  const cards = [
    {
      icon: Zap,
      title: 'Plain-English authoring',
      detail:
        'Type the rule the way the business says it. CogniDQ resolves columns, joins, and thresholds for you.',
      tone: 'brand',
    },
    {
      icon: TrendingUp,
      title: 'Score every dataset',
      detail:
        'A single DQ score per dataset, dimensional rollups, and a quality stability index that trends over time.',
      tone: 'info',
    },
    {
      icon: ShieldCheck,
      title: 'Audit-ready by design',
      detail:
        'Read-only execution, tenant isolation, durable evidence, and a complete log of who changed what.',
      tone: 'success',
    },
  ];
  return (
    <section className="py-12">
      <div className="grid gap-6 lg:grid-cols-3">
        {cards.map(({ icon: Icon, title, detail, tone }) => {
          const toneCls =
            tone === 'brand'
              ? 'bg-brand-soft text-brand'
              : tone === 'info'
                ? 'bg-info-soft text-info'
                : 'bg-success-soft text-success';
          return (
            <div
              key={title}
              className="group relative overflow-hidden rounded-xl border border-edge bg-surface-raised p-6 transition-all hover:-translate-y-1 hover:border-brand hover:shadow-lg"
            >
              <div className={`inline-flex h-11 w-11 items-center justify-center rounded-lg ${toneCls}`}>
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 text-lg font-semibold text-content">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-content-muted">{detail}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ─── Capability sections ─────────────────────────────────────────────────────

interface CapabilityProps {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: string;
  bullets: string[];
  reverse?: boolean;
}

function Capability({ icon: Icon, eyebrow, title, description, bullets, reverse }: CapabilityProps) {
  return (
    <section className="py-16">
      <div className={`grid items-center gap-12 lg:grid-cols-2 ${reverse ? 'lg:[&>*:first-child]:order-2' : ''}`}>
        <div className="space-y-5">
          <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
            <Icon className="h-5 w-5" />
          </div>
          <p className="text-xs font-semibold uppercase tracking-widest text-brand">{eyebrow}</p>
          <h2 className="text-3xl font-bold leading-tight text-content">{title}</h2>
          <p className="text-base leading-relaxed text-content-muted">{description}</p>
          <ul className="space-y-2 text-sm text-content">
            {bullets.map((b) => (
              <li key={b} className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-success" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
        <VisualCard icon={Icon} title={title} />
      </div>
    </section>
  );
}

function VisualCard({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="relative">
      <div className="pointer-events-none absolute -inset-4 rounded-2xl bg-gradient-to-br from-brand/20 via-info/10 to-transparent blur-2xl" />
      <div className="relative overflow-hidden rounded-2xl border border-edge bg-surface-raised p-8 shadow-xl">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgb(var(--color-brand)/0.12),transparent_55%)]" />
        <div className="relative flex items-start gap-4">
          <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <Icon className="h-7 w-7" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-widest text-content-muted">
              Preview
            </p>
            <p className="mt-1 text-lg font-semibold text-content">{title}</p>
          </div>
        </div>
        <div className="relative mt-6 space-y-2">
          {[78, 92, 65, 88].map((w, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-overlay">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-brand to-info"
                  style={{ width: `${w}%` }}
                />
              </div>
              <span className="w-10 text-right text-xs text-content-muted">{w}%</span>
            </div>
          ))}
        </div>
        <div className="relative mt-6 grid grid-cols-3 gap-2 text-center">
          {['Pass', 'Warn', 'Fail'].map((l, i) => (
            <div
              key={l}
              className={`rounded-lg border p-2 ${
                i === 0
                  ? 'border-success/30 bg-success-soft text-success'
                  : i === 1
                    ? 'border-warning/30 bg-warning-soft text-warning'
                    : 'border-danger/30 bg-danger-soft text-danger'
              }`}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wider">{l}</p>
              <p className="text-sm font-bold">{[112, 8, 2][i]}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const CAPABILITIES: CapabilityProps[] = [
  {
    icon: Sparkles,
    eyebrow: 'Capability 01',
    title: 'Natural-language rule builder',
    description:
      'Write what you mean — "customers in EU must have a valid VAT" — and CogniDQ produces an executable check, with the SQL, the assumptions, and a trust score you can audit.',
    bullets: [
      'Plain-English authoring with clarifying questions when intent is ambiguous',
      'Multi-obligation decomposition (AND / OR) handled automatically',
      'Per-decision explainability: rule type, subject, scope, glossary signals',
    ],
  },
  {
    icon: BookOpen,
    eyebrow: 'Capability 02',
    title: 'Metadata & context',
    description:
      'Every check links back to the source: schema, business glossary, owner, criticality. The AI uses this context to resolve ambiguous terms and route alerts to the right people.',
    bullets: [
      'Auto-discovered tables, columns, and freshness signals per connection',
      'Business glossary import (CSV) and per-tenant synonyms',
      'Asset cards with lineage, ownership, sensitivity classification',
    ],
    reverse: true,
  },
  {
    icon: Workflow,
    eyebrow: 'Capability 03',
    title: 'Quality flow generation',
    description:
      'A parsed rule becomes a flow graph: sources, joins, filters, checks, and thresholds. Edit the canvas when needed; the underlying definition stays serializable and version-controlled.',
    bullets: [
      'Visual flow builder with source / check / join / filter / aggregate nodes',
      'Thresholds with pass / warn / fail bands and expected outcomes',
      'Round-trip between natural language and flow without losing fidelity',
    ],
  },
  {
    icon: PlayCircle,
    eyebrow: 'Capability 04',
    title: 'Execution engine',
    description:
      'Read-only execution against your sources with cross-source joins, sampling, and parallel nodes. Designed for the warehouse, but pluggable to lake, OLTP, and files.',
    bullets: [
      'Postgres, MySQL, MSSQL, Oracle, Snowflake, BigQuery connectors',
      'Direct or agent-tunnel mode for private VPCs',
      'Per-execution evidence: rows scanned, failing samples, query duration',
    ],
    reverse: true,
  },
  {
    icon: Gauge,
    eyebrow: 'Capability 05',
    title: 'Monitoring & dashboards',
    description:
      'A single DQ score per dataset, dimensional rollups for the executive view, and drill-downs to the failing rows. Quality stability index trends over time.',
    bullets: [
      'KQI suite: coverage, governance maturity, operational summary',
      'Per-dataset profile: dimension scores, worst check, days since healthy',
      'Timeline views for executions, issues, and pass-rate trends',
    ],
  },
  {
    icon: Bug,
    eyebrow: 'Capability 06',
    title: 'Issue management',
    description:
      'Every failing check raises an issue with severity, owner, due date, and resolution path. Group related issues into an incident when a single root cause is in play.',
    bullets: [
      'Severity (critical / major / minor / informational) with SLAs',
      'Assignees, comments, status transitions, due dates',
      'Incident grouping for cross-issue investigations',
    ],
    reverse: true,
  },
  {
    icon: FileSearch,
    eyebrow: 'Capability 07',
    title: 'Evidence & audit trail',
    description:
      'Faulty rows, the SQL that found them, and the user who authored the rule — every artifact is durable, queryable, and exportable for the auditor.',
    bullets: [
      'Per-execution failing samples (bounded and tenant-controlled)',
      'Full audit log of mutations: who, what, when, from where',
      'Exportable evidence packages for SOX / DAMA / regulator reviews',
    ],
  },
  {
    icon: BellRing,
    eyebrow: 'Capability 08',
    title: 'Alerting & escalation',
    description:
      'Critical failures fan out to the people who can act: email, Slack, webhook. Alert rules pick channels and recipients per trigger; escalation policies cover the gaps.',
    bullets: [
      'Email, Slack, and generic webhook channels with per-channel test send',
      'Per-rule recipient + channel selection, retry with backoff',
      'In-product notification bell for in-session awareness',
    ],
    reverse: true,
  },
];

// ─── Personas ────────────────────────────────────────────────────────────────

const PERSONAS = [
  {
    title: 'Data Steward',
    summary: 'Owns rules and definitions. Writes them in plain English; trusts the AI to translate.',
    wins: ['Author in minutes, not days', 'Glossary-first workflow', 'Explainable parses'],
    accent: 'brand',
  },
  {
    title: 'Data Engineer',
    summary: 'Maintains pipelines and connections. Wants flow primitives, parallelism, and clean failure semantics.',
    wins: ['Pluggable connectors', 'Flow canvas with versioning', 'Read-only by design'],
    accent: 'info',
  },
  {
    title: 'Analytics Lead',
    summary: 'Reports trust to the business. Needs scores, trends, and a clear story for the CFO.',
    wins: ['KQI dashboards', 'Quality stability index', 'Export-ready evidence'],
    accent: 'success',
  },
  {
    title: 'Compliance / Audit',
    summary: 'Cares about who did what, when, and to which data. Demands durable artifacts.',
    wins: ['Full audit log', 'Faulty-row evidence', 'RBAC with workspace scope'],
    accent: 'warning',
  },
];

function Personas() {
  return (
    <section className="py-16">
      <SectionHeading
        eyebrow="Who it's for"
        title="One product, four daily workflows"
        subtitle="CogniDQ is shaped around the people who actually live with data quality every week."
      />
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {PERSONAS.map((p) => {
          const accentBar =
            p.accent === 'brand'
              ? 'from-brand to-brand-hover'
              : p.accent === 'info'
                ? 'from-info to-brand'
                : p.accent === 'success'
                  ? 'from-success to-info'
                  : 'from-warning to-danger';
          return (
            <div
              key={p.title}
              className="group relative flex h-full flex-col overflow-hidden rounded-xl border border-edge bg-surface-raised p-6 transition-all hover:-translate-y-1 hover:border-brand hover:shadow-lg"
            >
              <span className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${accentBar}`} />
              <h3 className="text-lg font-semibold text-content">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-content-muted">{p.summary}</p>
              <ul className="mt-4 space-y-1.5 text-sm text-content">
                {p.wins.map((w) => (
                  <li key={w} className="flex items-start gap-2">
                    <ChevronRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand" />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ─── Journey ─────────────────────────────────────────────────────────────────

const JOURNEY = [
  { step: '01', title: 'Connect a source', detail: 'Postgres, Snowflake, BigQuery, and more — direct or agent mode.' },
  { step: '02', title: 'Import a glossary', detail: 'Bring your terms; we resolve column synonyms automatically.' },
  { step: '03', title: 'Write your first rule', detail: 'Type a sentence; pick from clarifying questions when needed.' },
  { step: '04', title: 'Generate a flow', detail: 'Inspect the canvas, tune thresholds, save as a versioned definition.' },
  { step: '05', title: 'Execute & inspect', detail: 'Sample or full-run; review failing rows; pin to an issue.' },
  { step: '06', title: 'Alert the right people', detail: 'Email, Slack, webhook — per rule, per workspace, with retries.' },
];

function Journey() {
  return (
    <section className="py-16">
      <SectionHeading eyebrow="From zero to alerting" title="A six-step path your team can finish in an afternoon" />
      <ol className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {JOURNEY.map((j) => (
          <li
            key={j.step}
            className="group relative rounded-xl border border-edge bg-surface-raised p-6 transition-all hover:-translate-y-0.5 hover:border-brand hover:shadow-md"
          >
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft text-sm font-bold text-brand">
              {j.step}
            </span>
            <h3 className="mt-4 text-base font-semibold text-content">{j.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-content-muted">{j.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ─── Ecosystem ───────────────────────────────────────────────────────────────

function Ecosystem() {
  return (
    <section className="py-16">
      <SectionHeading
        eyebrow="Where it fits"
        title="Sits between your sources and the people who act on quality"
      />
      <div className="mt-10 rounded-2xl border border-edge bg-surface-raised p-8 lg:p-12">
        <svg
          viewBox="0 0 800 360"
          role="img"
          aria-label="CogniDQ ecosystem diagram: sources flow into CogniDQ, which dispatches alerts to people and tools"
          className="mx-auto h-auto w-full max-w-3xl"
        >
          <g fontFamily="ui-sans-serif, system-ui, sans-serif" fontSize="13">
            <text x="80" y="40" textAnchor="middle" className="fill-content" fontWeight="600">Sources</text>
            {[
              { y: 70, label: 'Postgres' },
              { y: 120, label: 'Snowflake' },
              { y: 170, label: 'BigQuery' },
              { y: 220, label: 'MSSQL / Oracle' },
              { y: 270, label: 'Files (CSV / Parquet)' },
            ].map((s) => (
              <g key={s.label}>
                <rect x="10" y={s.y} width="150" height="36" rx="8" className="fill-surface stroke-edge-strong" strokeWidth="1" />
                <text x="85" y={s.y + 23} textAnchor="middle" className="fill-content">{s.label}</text>
              </g>
            ))}
            <rect x="320" y="120" width="160" height="120" rx="14" className="fill-brand-soft stroke-brand" strokeWidth="2" />
            <text x="400" y="170" textAnchor="middle" className="fill-brand" fontSize="16" fontWeight="700">CogniDQ</text>
            <text x="400" y="192" textAnchor="middle" className="fill-content-muted" fontSize="11">Parse · Generate</text>
            <text x="400" y="208" textAnchor="middle" className="fill-content-muted" fontSize="11">Execute · Score</text>
            <text x="720" y="40" textAnchor="middle" className="fill-content" fontWeight="600">People &amp; tools</text>
            {[
              { y: 70, label: 'Email' },
              { y: 120, label: 'Slack' },
              { y: 170, label: 'Webhook' },
              { y: 220, label: 'Dashboards' },
              { y: 270, label: 'Audit / SIEM' },
            ].map((d) => (
              <g key={d.label}>
                <rect x="640" y={d.y} width="150" height="36" rx="8" className="fill-surface stroke-edge-strong" strokeWidth="1" />
                <text x="715" y={d.y + 23} textAnchor="middle" className="fill-content">{d.label}</text>
              </g>
            ))}
            {[88, 138, 188, 238, 288].map((y) => (
              <path key={`l-${y}`} d={`M160 ${y} C 240 ${y}, 280 180, 320 180`} fill="none" className="stroke-brand/50" strokeWidth="1.5" />
            ))}
            {[88, 138, 188, 238, 288].map((y) => (
              <path key={`r-${y}`} d={`M480 180 C 560 180, 580 ${y}, 640 ${y}`} fill="none" className="stroke-info/50" strokeWidth="1.5" />
            ))}
          </g>
        </svg>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-content-muted">
          <span className="inline-flex items-center gap-1.5"><Database className="h-3.5 w-3.5 text-brand" /> Read-only</span>
          <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-success" /> Tenant-isolated</span>
          <span className="inline-flex items-center gap-1.5"><Slack className="h-3.5 w-3.5 text-info" /> Slack-native alerts</span>
          <span className="inline-flex items-center gap-1.5"><Mail className="h-3.5 w-3.5 text-info" /> Email delivery</span>
          <span className="inline-flex items-center gap-1.5"><Webhook className="h-3.5 w-3.5 text-info" /> Generic webhooks</span>
        </div>
      </div>
    </section>
  );
}

// ─── Testimonials ────────────────────────────────────────────────────────────

function Testimonials() {
  const quotes = [
    {
      quote:
        "We replaced three spreadsheets and a Python script with a single CogniDQ flow. The auditor signed off in one meeting.",
      author: 'Head of Data Governance',
      org: 'Global Insurance, EU',
    },
    {
      quote:
        "Our stewards now author rules in English. Engineering still owns the flows, but the backlog is gone.",
      author: 'Director of Data Platform',
      org: 'Retail, North America',
    },
    {
      quote:
        "The trust score per dataset is the first metric our CFO actually understands. That's worth the license alone.",
      author: 'VP Analytics',
      org: 'FinTech, APAC',
    },
  ];
  return (
    <section className="py-16">
      <SectionHeading
        eyebrow="Voices from the field"
        title="Trusted by data teams that move fast and audit slow"
      />
      <div className="mt-10 grid gap-6 lg:grid-cols-3">
        {quotes.map((q) => (
          <figure
            key={q.author}
            className="relative flex h-full flex-col rounded-xl border border-edge bg-surface-raised p-6 shadow-sm transition-all hover:border-brand hover:shadow-md"
          >
            <Quote className="absolute right-5 top-5 h-8 w-8 text-brand/15" />
            <div className="flex gap-0.5 text-warning">
              {Array.from({ length: 5 }).map((_, i) => (
                <Star key={i} className="h-4 w-4 fill-current" />
              ))}
            </div>
            <blockquote className="mt-4 flex-1 text-sm leading-relaxed text-content">
              "{q.quote}"
            </blockquote>
            <figcaption className="mt-5 border-t border-edge pt-4">
              <p className="text-sm font-semibold text-content">{q.author}</p>
              <p className="text-xs text-content-muted">{q.org}</p>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

// ─── Trust banner + closing CTA ──────────────────────────────────────────────

function TrustBanner() {
  const badges = [
    { icon: ShieldCheck, label: 'Read-only by default' },
    { icon: Lock, label: 'Tenant-isolated' },
    { icon: Activity, label: 'Full audit trail' },
    { icon: Cloud, label: 'SaaS or self-hosted' },
    { icon: Server, label: 'Agent tunnel for private VPCs' },
  ];
  return (
    <section className="py-12">
      <div className="rounded-2xl border border-edge bg-surface-raised p-8 text-center">
        <ShieldCheck className="mx-auto h-8 w-8 text-success" />
        <h3 className="mt-3 text-2xl font-semibold text-content">Built for the auditor in the room</h3>
        <p className="mx-auto mt-2 max-w-2xl text-sm leading-relaxed text-content-muted">
          Read-only by default, tenant-isolated, with a full audit trail. See our trust posture for the details.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-content-muted">
          {badges.map(({ icon: Icon, label }) => (
            <span key={label} className="inline-flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5 text-brand" /> {label}
            </span>
          ))}
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link to="/trust" className="text-sm font-semibold text-brand hover:underline">Trust center →</Link>
          <Link to="/security" className="text-sm font-semibold text-brand hover:underline">Security →</Link>
          <Link to="/privacy" className="text-sm font-semibold text-brand hover:underline">Privacy →</Link>
        </div>
      </div>
    </section>
  );
}

function ClosingCta() {
  return (
    <section className="my-16 overflow-hidden rounded-3xl bg-gradient-to-br from-brand via-brand-hover to-info p-12 text-center text-white shadow-2xl">
      <div className="relative">
        <Sparkles className="mx-auto h-8 w-8 text-white/80" />
        <h2 className="mt-4 text-3xl font-bold tracking-tight lg:text-4xl">
          Bring trust to your data — start with one rule
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-base text-white/90">
          Open the Hub and follow the six-step onboarding. No SQL required.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link to="/hub" className="group inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-base font-semibold text-brand shadow-lg transition-all hover:shadow-xl">
            Start onboarding
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link to="/request-demo" className="inline-flex items-center gap-2 rounded-lg border border-white/40 px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-white/10">
            Talk to sales
          </Link>
        </div>
      </div>
    </section>
  );
}

// ─── Helpers + Page ──────────────────────────────────────────────────────────

function SectionHeading({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {
  return (
    <div className="text-center">
      <p className="text-xs font-semibold uppercase tracking-widest text-brand">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-content lg:text-4xl">{title}</h2>
      {subtitle ? (
        <p className="mx-auto mt-3 max-w-2xl text-base leading-relaxed text-content-muted">{subtitle}</p>
      ) : null}
    </div>
  );
}

export default function Home() {
  return (
    <div className="text-content">
      <Hero />
      <MetricsBar />
      <FeatureHighlights />
      {CAPABILITIES.map((cap) => (
        <Capability key={cap.title} {...cap} />
      ))}
      <Personas />
      <Journey />
      <Ecosystem />
      <Testimonials />
      <TrustBanner />
      <ClosingCta />
    </div>
  );
}
