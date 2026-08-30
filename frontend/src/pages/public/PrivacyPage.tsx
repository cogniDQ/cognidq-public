import PublicPageShell, {
  PublicSection,
} from '../../components/public/PublicPageShell';

export default function PrivacyPage() {
  return (
    <PublicPageShell
      eyebrow="Trust · Privacy"
      title="Privacy notice"
      subtitle="A plain-English summary of how CogniDQ handles personal and customer data. The formal data processing agreement is available on request."
    >
      <PublicSection title="What we process">
        We process metadata required to operate the service: dataset names and schemas,
        check definitions, execution telemetry (pass/fail counts, durations), and a bounded
        sample of failing rows when an issue is raised. We do not bulk-export customer data.
      </PublicSection>
      <PublicSection title="What we don't do">
        We do not sell personal data. We do not train shared models on a customer's data.
        Per-tenant feature learning, when enabled, is scoped to that tenant.
      </PublicSection>
      <PublicSection title="Retention">
        Execution telemetry is retained for the term of the contract plus 30 days for backup
        rotation. Failing-row evidence is retained per dataset retention policy, which the
        customer controls.
      </PublicSection>
      <PublicSection title="Sub-processors">
        A live list of sub-processors (cloud hosting, email delivery, error monitoring) is
        available on request.
      </PublicSection>
      <PublicSection title="Contact the Data Protection Officer">
        <a className="text-brand hover:underline" href="mailto:privacy@cognidq.example">
          privacy@cognidq.example
        </a>
      </PublicSection>
    </PublicPageShell>
  );
}
