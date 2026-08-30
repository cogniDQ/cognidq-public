import { Mail, Building2, BookOpen, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import PublicPageShell from '../../components/public/PublicPageShell';

const channels = [
  {
    icon: Mail,
    title: 'General',
    description: 'Product, partnerships, and press.',
    href: 'mailto:hello@cognidq.example',
    label: 'hello@cognidq.example',
  },
  {
    icon: Building2,
    title: 'Sales',
    description: 'Pricing, procurement, and pilots.',
    href: '/request-demo',
    label: 'Request a demo →',
  },
  {
    icon: ShieldCheck,
    title: 'Security',
    description: 'Disclosure and pen-test reports.',
    href: 'mailto:security@cognidq.example',
    label: 'security@cognidq.example',
  },
  {
    icon: BookOpen,
    title: 'Support',
    description: 'For existing customers.',
    href: 'mailto:support@cognidq.example',
    label: 'support@cognidq.example',
  },
];

export default function ContactPage() {
  return (
    <PublicPageShell
      eyebrow="Contact"
      title="Talk to our team"
      subtitle="Pick the channel that matches your question. For procurement or security paperwork, please include your company name in the subject line."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {channels.map((c) => {
          const Icon = c.icon;
          const isInternal = c.href.startsWith('/');
          const inner = (
            <div className="flex h-full flex-col rounded-lg border border-edge bg-surface-raised p-5 transition-colors hover:border-brand">
              <Icon className="h-5 w-5 text-brand" />
              <h2 className="mt-3 text-base font-semibold text-content">{c.title}</h2>
              <p className="mt-1 text-sm text-content-muted">{c.description}</p>
              <p className="mt-4 text-sm font-medium text-brand">{c.label}</p>
            </div>
          );
          return isInternal ? (
            <Link key={c.title} to={c.href}>
              {inner}
            </Link>
          ) : (
            <a key={c.title} href={c.href}>
              {inner}
            </a>
          );
        })}
      </div>
    </PublicPageShell>
  );
}
