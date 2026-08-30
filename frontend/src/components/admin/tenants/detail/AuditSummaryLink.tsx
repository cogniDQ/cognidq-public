/**
 * AuditSummaryLink — a link to the tenant's audit log listing page.
 *
 * Always present. Points to the frontend /admin/tenants/:tenant_id/audit-logs
 * route which will be built in a future packet.
 * Part of the Tenant Detail page (Packet 12).
 */
import { Link } from 'react-router-dom';
import { ClipboardList } from 'lucide-react';

interface Props {
  tenantId: string;
}

export default function AuditSummaryLink({ tenantId }: Props) {
  return (
    <Link
      to={`/admin/tenants/${tenantId}/audit-logs`}
      className="inline-flex items-center gap-2 text-sm text-primary-400 hover:text-primary-300 transition-colors"
      data-testid="audit-summary-link"
    >
      <ClipboardList className="w-4 h-4" aria-hidden="true" />
      View Audit Logs
    </Link>
  );
}
