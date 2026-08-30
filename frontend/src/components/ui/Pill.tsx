import type { ReactNode } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Info,
  Pause,
  type LucideIcon,
} from 'lucide-react';

export type PillTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger'
  | 'brand';

export interface PillProps {
  tone?: PillTone;
  icon?: LucideIcon | null;
  dot?: boolean;
  children: ReactNode;
  className?: string;
  size?: 'sm' | 'md';
}

const TONE_STYLES: Record<PillTone, string> = {
  neutral: 'bg-edge-subtle text-content-muted ring-edge',
  info: 'bg-info-soft text-info ring-info/30',
  success: 'bg-success-soft text-success ring-success/30',
  warning: 'bg-warning-soft text-warning ring-warning/30',
  danger: 'bg-danger-soft text-danger ring-danger/30',
  brand: 'bg-brand-soft text-brand ring-brand/30',
};

const TONE_DOT: Record<PillTone, string> = {
  neutral: 'bg-content-subtle',
  info: 'bg-info',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  brand: 'bg-brand',
};

const SIZE: Record<NonNullable<PillProps['size']>, string> = {
  sm: 'px-2 py-0.5 text-[11px]',
  md: 'px-2.5 py-1 text-xs',
};

/**
 * Generic semantic pill. Use directly or via the higher-level
 * <SeverityPill /> and <StatusPill /> wrappers.
 */
export function Pill({
  tone = 'neutral',
  icon: Icon,
  dot = false,
  children,
  className = '',
  size = 'md',
}: PillProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset ${TONE_STYLES[tone]} ${SIZE[size]} ${className}`}
    >
      {dot ? (
        <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]}`} aria-hidden />
      ) : null}
      {Icon ? <Icon className="h-3 w-3" aria-hidden /> : null}
      <span>{children}</span>
    </span>
  );
}

// ─── Severity ────────────────────────────────────────────────────────────────

export type Severity = 'critical' | 'major' | 'minor' | 'informational';

const SEVERITY_MAP: Record<
  Severity,
  { tone: PillTone; icon: LucideIcon; label: string }
> = {
  critical: { tone: 'danger', icon: AlertOctagon, label: 'Critical' },
  major: { tone: 'warning', icon: AlertTriangle, label: 'Major' },
  minor: { tone: 'info', icon: Info, label: 'Minor' },
  informational: { tone: 'neutral', icon: Info, label: 'Informational' },
};

export function SeverityPill({
  severity,
  size = 'md',
}: {
  severity: Severity | string;
  size?: 'sm' | 'md';
}) {
  const key = (severity?.toLowerCase() as Severity) ?? 'informational';
  const cfg = SEVERITY_MAP[key] ?? SEVERITY_MAP.informational;
  return (
    <Pill tone={cfg.tone} icon={cfg.icon} size={size}>
      {cfg.label}
    </Pill>
  );
}

// ─── Status ──────────────────────────────────────────────────────────────────

export type StatusKind =
  | 'active'
  | 'enabled'
  | 'success'
  | 'completed'
  | 'passed'
  | 'running'
  | 'pending'
  | 'queued'
  | 'draft'
  | 'paused'
  | 'inactive'
  | 'disabled'
  | 'archived'
  | 'failed'
  | 'error'
  | 'cancelled'
  | 'warning';

const STATUS_MAP: Record<
  StatusKind,
  { tone: PillTone; icon?: LucideIcon | null; label?: string }
> = {
  active: { tone: 'success', icon: CheckCircle2 },
  enabled: { tone: 'success', icon: CheckCircle2 },
  success: { tone: 'success', icon: CheckCircle2 },
  completed: { tone: 'success', icon: CheckCircle2 },
  passed: { tone: 'success', icon: CheckCircle2 },
  running: { tone: 'info', icon: CircleDashed },
  pending: { tone: 'info', icon: CircleDashed },
  queued: { tone: 'neutral', icon: CircleDashed },
  draft: { tone: 'neutral', icon: null },
  paused: { tone: 'warning', icon: Pause },
  inactive: { tone: 'neutral', icon: null },
  disabled: { tone: 'neutral', icon: null },
  archived: { tone: 'neutral', icon: null },
  failed: { tone: 'danger', icon: AlertOctagon },
  error: { tone: 'danger', icon: AlertOctagon },
  cancelled: { tone: 'neutral', icon: null },
  warning: { tone: 'warning', icon: AlertTriangle },
};

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function StatusPill({
  status,
  size = 'md',
  dot = true,
}: {
  status: StatusKind | string;
  size?: 'sm' | 'md';
  dot?: boolean;
}) {
  const key = (status?.toLowerCase() as StatusKind) ?? 'inactive';
  const cfg = STATUS_MAP[key] ?? { tone: 'neutral' as PillTone, icon: null };
  return (
    <Pill tone={cfg.tone} icon={cfg.icon ?? undefined} dot={dot && !cfg.icon} size={size}>
      {cfg.label ?? titleCase(String(status ?? 'unknown'))}
    </Pill>
  );
}

export default Pill;
