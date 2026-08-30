import PublicPageShell, {
  PublicSection,
} from '../../components/public/PublicPageShell';

export default function SecurityPage() {
  return (
    <PublicPageShell
      eyebrow="Trust · Security"
      title="Built for enterprise data security"
      subtitle="CogniDQ executes data quality checks against your data sources without ever copying or persisting customer rows."
    >
      <PublicSection title="Read-only by default">
        Connections are opened with least-privilege credentials. Generated SQL is
        executed read-only; we never issue <code className="rounded bg-edge-subtle px-1 py-0.5 text-xs">INSERT</code>,
        <code className="ml-1 rounded bg-edge-subtle px-1 py-0.5 text-xs">UPDATE</code>, or
        <code className="ml-1 rounded bg-edge-subtle px-1 py-0.5 text-xs">DELETE</code> statements on customer data.
      </PublicSection>
      <PublicSection title="Tenant isolation">
        Every row in our control plane carries a <code className="rounded bg-edge-subtle px-1 py-0.5 text-xs">tenant_id</code> and
        is enforced at the API, service, and database layer via row-level filters.
      </PublicSection>
      <PublicSection title="Credential handling">
        Source credentials are encrypted at rest using envelope encryption. The data plane
        decrypts only in-memory at execution time; nothing is logged.
      </PublicSection>
      <PublicSection title="Audit & RBAC">
        Every mutation produces an audit event with actor, action, target, IP, and timestamp.
        Roles are scoped per workspace; platform administrators have a separate stripe and
        cannot impersonate tenant users without an explicit, audited grant.
      </PublicSection>
      <PublicSection title="Reporting a vulnerability">
        Email <a className="text-brand hover:underline" href="mailto:security@cognidq.example">security@cognidq.example</a>.
        We acknowledge within one business day and follow coordinated disclosure.
      </PublicSection>
    </PublicPageShell>
  );
}
