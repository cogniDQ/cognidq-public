import { CheckCircle2 } from 'lucide-react';
import PublicPageShell from '../../components/public/PublicPageShell';

const components = [
  { name: 'API (control plane)', uptime: '99.98%' },
  { name: 'Web app', uptime: '99.99%' },
  { name: 'Execution engine', uptime: '99.95%' },
  { name: 'Alert dispatch', uptime: '99.97%' },
];

export default function StatusPage() {
  return (
    <PublicPageShell
      eyebrow="Trust · Status"
      title="System status"
      subtitle="All systems operational. This is a static stub for the upcoming live status board."
    >
      <div className="rounded-lg border border-success/40 bg-success-soft p-5">
        <div className="flex items-center gap-3 text-success">
          <CheckCircle2 className="h-5 w-5" />
          <p className="text-base font-semibold">All systems operational</p>
        </div>
        <p className="mt-1 text-sm text-content-muted">
          Live status, incident history, and a public RSS feed will be wired in once the
          status provider is selected.
        </p>
      </div>

      <div className="overflow-hidden rounded-lg border border-edge">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-raised text-content-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Component</th>
              <th className="px-4 py-3 font-medium">90-day uptime</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {components.map((c) => (
              <tr key={c.name} className="bg-surface">
                <td className="px-4 py-3 text-content">{c.name}</td>
                <td className="px-4 py-3 text-content-muted">{c.uptime}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-medium text-success ring-1 ring-inset ring-success/30">
                    <span className="h-1.5 w-1.5 rounded-full bg-success" />
                    Operational
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PublicPageShell>
  );
}
