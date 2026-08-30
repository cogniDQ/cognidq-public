import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** Override the default vertical padding. */
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  testId?: string;
}

const SIZE_PAD: Record<NonNullable<EmptyStateProps['size']>, string> = {
  sm: 'py-10',
  md: 'py-16',
  lg: 'py-24',
};

/**
 * Standardised empty-state card. Drop into any list/table when there are no rows.
 *
 * Example:
 *   <EmptyState
 *     icon={Bell}
 *     title="No alert rules yet"
 *     description="Create a rule to start dispatching notifications."
 *     action={<button className="btn btn-primary">New rule</button>}
 *   />
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  size = 'md',
  className,
  testId,
}: EmptyStateProps) {
  return (
    <div
      data-testid={testId ?? 'empty-state'}
      className={`flex flex-col items-center justify-center text-center ${SIZE_PAD[size]} ${className ?? ''}`}
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-edge-subtle text-content-muted">
        <Icon className="h-6 w-6" aria-hidden />
      </div>
      <p className="mb-1 text-base font-semibold text-content">{title}</p>
      {description ? (
        <p className="max-w-md text-sm text-content-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export default EmptyState;
