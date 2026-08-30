/**
 * EmptyState — generic empty/error/loading-aware placeholder for list and dashboard views.
 *
 * D2: provides a primary CTA (e.g. "Create rule", "Open builder") that helps users
 * progress from a zero-state instead of staring at an empty table.
 * D3: separate visual treatment for an `error` (red border, retry CTA) vs an `empty`
 * (muted, neutral, primary CTA) state so users can tell which they're looking at.
 *
 * Usage:
 *   <EmptyState
 *     icon={ShieldAlert}
 *     title="No incidents yet"
 *     description="Critical issues automatically open incidents..."
 *     primaryAction={{ label: 'Create incident', to: '...', icon: Plus }}
 *     secondaryAction={{ label: 'Configure policy', to: '...' }}
 *   />
 *
 *   <EmptyState variant="error" title="Couldn't load incidents" onRetry={refetch} />
 */
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { Inbox, AlertTriangle, RefreshCw } from 'lucide-react';

type Variant = 'empty' | 'error';

interface ActionConfig {
  label: string;
  to?: string;
  onClick?: () => void;
  icon?: LucideIcon;
}

interface Props {
  variant?: Variant;
  /** Lucide icon. Defaults to Inbox for empty, AlertTriangle for error. */
  icon?: LucideIcon;
  title: string;
  description?: string;
  primaryAction?: ActionConfig;
  secondaryAction?: ActionConfig;
  tertiaryAction?: ActionConfig;
  /** When variant=error, optional retry handler shown as a button. */
  onRetry?: () => void;
  className?: string;
  testId?: string;
}

function ActionButton({ action, primary }: { action: ActionConfig; primary: boolean }) {
  const Icon = action.icon;
  const baseCls = primary
    ? 'inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors'
    : 'inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-gray-600 bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-medium transition-colors';

  if (action.to) {
    return (
      <Link to={action.to} className={baseCls}>
        {Icon && <Icon className="w-4 h-4" />}
        {action.label}
      </Link>
    );
  }
  return (
    <button type="button" onClick={action.onClick} className={baseCls}>
      {Icon && <Icon className="w-4 h-4" />}
      {action.label}
    </button>
  );
}

export default function EmptyState({
  variant = 'empty',
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  tertiaryAction,
  onRetry,
  className,
  testId,
}: Props) {
  const isError = variant === 'error';
  const Icon = icon ?? (isError ? AlertTriangle : Inbox);

  const wrapperCls = isError
    ? 'flex flex-col items-center justify-center text-center py-12 px-6 rounded-2xl border border-red-500/30 bg-red-500/5'
    : 'flex flex-col items-center justify-center text-center py-16 px-6 rounded-2xl border border-dashed border-gray-700 bg-gray-800/30';

  const iconCls = isError ? 'w-12 h-12 text-red-400 mb-4' : 'w-12 h-12 text-gray-600 mb-4';

  return (
    <div
      className={`${wrapperCls} ${className ?? ''}`.trim()}
      data-testid={testId ?? (isError ? 'empty-state-error' : 'empty-state')}
      role={isError ? 'alert' : undefined}
    >
      <Icon className={iconCls} aria-hidden="true" />
      <p className={`text-lg font-medium mb-1 ${isError ? 'text-red-300' : 'text-gray-200'}`}>
        {title}
      </p>
      {description && (
        <p className="text-sm text-gray-500 max-w-md mb-6">{description}</p>
      )}

      {!isError && (primaryAction || secondaryAction || tertiaryAction) && (
        <div className="flex flex-wrap items-center justify-center gap-3">
          {primaryAction && <ActionButton action={primaryAction} primary />}
          {secondaryAction && <ActionButton action={secondaryAction} primary={false} />}
          {tertiaryAction && <ActionButton action={tertiaryAction} primary={false} />}
        </div>
      )}

      {isError && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-red-400/40 bg-red-500/10 hover:bg-red-500/20 text-red-200 text-sm font-medium transition-colors"
          data-testid="empty-state-retry"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      )}
    </div>
  );
}
