/**
 * TenantCountsSection — displays workspace_count and user_count.
 *
 * When *_count_available = false (registry timed out or failed), an explicit
 * "count unavailable" indicator is shown instead of the bare number 0.
 * Displaying 0 when the registry is down would mislead the user into thinking
 * there are genuinely no workspaces/users (TDD §3.4 constraint).
 *
 * Part of the Tenant Detail page (Packet 12).
 */
import { AlertTriangle } from 'lucide-react';
import { TenantDetailRecord } from '../../../../services/tenant';

interface Props {
  tenant: TenantDetailRecord;
}

interface CountDisplayProps {
  count: number;
  available: boolean;
  label: string;
  testId: string;
  unavailableTestId: string;
}

function CountDisplay({ count, available, label, testId, unavailableTestId }: CountDisplayProps) {
  if (!available) {
    return (
      <div>
        <dt className="text-xs text-gray-500 mb-1">{label}</dt>
        <dd
          className="flex items-center gap-1.5 text-sm text-amber-400"
          data-testid={unavailableTestId}
          role="status"
          aria-label={`${label}: count unavailable`}
        >
          <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>Count unavailable</span>
        </dd>
      </div>
    );
  }

  return (
    <div>
      <dt className="text-xs text-gray-500 mb-0.5">{label}</dt>
      <dd className="text-2xl font-semibold text-gray-100" data-testid={testId}>
        {count.toLocaleString()}
      </dd>
    </div>
  );
}

export default function TenantCountsSection({ tenant }: Props) {
  return (
    <section aria-labelledby="counts-heading" data-testid="section-counts">
      <h2 id="counts-heading" className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">
        Usage
      </h2>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <CountDisplay
          count={tenant.workspace_count}
          available={tenant.workspace_count_available}
          label="Workspaces"
          testId="detail-workspace-count"
          unavailableTestId="workspace-count-unavailable"
        />
        <CountDisplay
          count={tenant.user_count}
          available={tenant.user_count_available}
          label="Users"
          testId="detail-user-count"
          unavailableTestId="user-count-unavailable"
        />
      </dl>
    </section>
  );
}
