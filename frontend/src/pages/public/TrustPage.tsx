import PublicPageShell, {
  PublicSection,
} from '../../components/public/PublicPageShell';

export default function TrustPage() {
  return (
    <PublicPageShell
      eyebrow="Trust"
      title="Trust at CogniDQ"
      subtitle="One page that links to everything an enterprise buyer needs before signing: security posture, privacy controls, uptime, and how to reach us."
    >
      <PublicSection title="Architecture posture">
        CogniDQ is a multi-tenant SaaS with a tenant-isolated control plane and an
        ephemeral data plane that connects to your sources read-only. See{' '}
        <a className="text-brand hover:underline" href="/security">Security</a> for details.
      </PublicSection>
      <PublicSection title="Privacy &amp; data residency">
        We process only the metadata required to operate quality checks: schemas, sample
        violations, and execution telemetry. See{' '}
        <a className="text-brand hover:underline" href="/privacy">Privacy</a>.
      </PublicSection>
      <PublicSection title="Reliability">
        We publish current status, planned maintenance, and historical incidents at{' '}
        <a className="text-brand hover:underline" href="/status">Status</a>.
      </PublicSection>
      <PublicSection title="Talk to a human">
        Procurement questions, custom contracts, and pen-test reports are routed via{' '}
        <a className="text-brand hover:underline" href="/contact">Contact</a>.
      </PublicSection>
    </PublicPageShell>
  );
}
