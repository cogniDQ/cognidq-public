import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface PublicPageShellProps {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}

/**
 * Shared chrome for stub public pages (Trust, Security, Privacy, Status, Contact).
 * Uses semantic theme tokens so it adapts to both light and dark modes.
 */
export default function PublicPageShell({
  eyebrow,
  title,
  subtitle,
  children,
}: PublicPageShellProps) {
  return (
    <div className="mx-auto max-w-4xl space-y-10 px-4 py-12 text-content">
      <header className="space-y-3">
        {eyebrow ? (
          <p className="text-xs font-semibold uppercase tracking-widest text-brand">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-4xl font-bold tracking-tight">{title}</h1>
        {subtitle ? (
          <p className="max-w-2xl text-lg text-content-muted">{subtitle}</p>
        ) : null}
      </header>

      <div className="space-y-8 text-base leading-relaxed text-content">
        {children}
      </div>

      <footer className="border-t border-edge pt-6 text-sm text-content-muted">
        Looking for something else?{' '}
        <Link to="/contact" className="text-brand hover:underline">
          Talk to our team
        </Link>
        .
      </footer>
    </div>
  );
}

export function PublicSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h2 className="text-xl font-semibold text-content">{title}</h2>
      <div className="text-content-muted">{children}</div>
    </section>
  );
}
