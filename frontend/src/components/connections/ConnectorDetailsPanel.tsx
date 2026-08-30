/**
 * F-CONN-UX — Selected connector details panel.
 *
 * Right-rail panel that explains, in plain English, what a customer gets
 * by connecting the selected connector. Driven entirely by the registry
 * `ConnectorSpec` so no per-connector branches live in the UI.
 *
 * Spec §8.
 */
import {
  CredentialField,
  CUSTOMER_STATUS_BADGE_CLASS,
  CUSTOMER_STATUS_LABEL,
  ConnectorSpec,
  customerCapabilitiesFor,
  customerStatusFor,
  CUSTOMER_GROUP_LABEL,
  customerGroupFor,
} from '../../services/connectorCatalogService';

interface ConnectorDetailsPanelProps {
  spec: ConnectorSpec | null;
  onConfigure: (spec: ConnectorSpec) => void;
  /** When true, also surface engineering metadata (priority, raw status). */
  adminMode?: boolean;
}

export default function ConnectorDetailsPanel({
  spec,
  onConfigure,
  adminMode = false,
}: ConnectorDetailsPanelProps) {
  if (!spec) {
    return (
      <aside
        data-testid="connector-details-panel"
        data-state="empty"
        className="h-full p-6 rounded-xl border border-dark-700 bg-dark-900 text-sm text-gray-400"
      >
        <p className="font-medium text-gray-300 mb-2">Pick a connector</p>
        <p>
          Select a connector on the left to see what it enables, what
          credentials are required, and how to configure it.
        </p>
      </aside>
    );
  }

  const status = customerStatusFor(spec);
  const capabilities = customerCapabilitiesFor(spec);
  const requiredFields = spec.credential_schema.filter((f) => f.required);
  const optionalFields = spec.credential_schema.filter((f) => !f.required);
  const isComingSoon = status === 'coming_soon';

  return (
    <aside
      data-testid="connector-details-panel"
      data-state="selected"
      data-connector={spec.type}
      className="h-full p-6 rounded-xl border border-dark-700 bg-dark-900 space-y-5"
    >
      <header>
        <p className="text-[11px] uppercase tracking-wide text-gray-500">
          {CUSTOMER_GROUP_LABEL[customerGroupFor(spec)]}
        </p>
        <div className="flex items-start justify-between gap-2 mt-1">
          <h2
            className="text-lg font-semibold text-gray-100"
            data-testid="details-display-name"
          >
            {spec.display_name}
          </h2>
          <span
            data-testid="details-status-badge"
            className={`text-[11px] uppercase tracking-wide border px-2 py-0.5 rounded flex-shrink-0 ${CUSTOMER_STATUS_BADGE_CLASS[status]}`}
          >
            {CUSTOMER_STATUS_LABEL[status]}
          </span>
        </div>
        <p className="mt-2 text-sm text-gray-400">{spec.description}</p>
      </header>

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
          What this enables
        </h3>
        <ul
          className="space-y-1 text-sm text-gray-300"
          data-testid="details-capabilities"
        >
          {capabilities.length === 0 ? (
            <li className="text-gray-500 italic">
              Capabilities will be announced when this connector ships.
            </li>
          ) : (
            capabilities.map((cap) => (
              <li
                key={cap.key}
                data-testid={`details-capability-${cap.key}`}
                className="flex items-start gap-2"
              >
                <span aria-hidden className="text-emerald-400">✓</span>
                {cap.label}
              </li>
            ))
          )}
        </ul>
      </section>

      {requiredFields.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
            You'll need
          </h3>
          <ul
            className="space-y-1 text-sm text-gray-300"
            data-testid="details-requirements"
          >
            {requiredFields.map((f) => (
              <li
                key={f.name}
                className="flex items-start gap-2"
                data-testid={`details-requirement-${f.name}`}
              >
                <span aria-hidden className="text-gray-500">•</span>
                <span>
                  <span className="font-medium">{f.label}</span>
                  {f.help_text && (
                    <span className="text-gray-500"> — {f.help_text}</span>
                  )}
                </span>
              </li>
            ))}
            {optionalFields.length > 0 && (
              <li className="text-xs text-gray-500 mt-1">
                Plus {optionalFields.length} optional setting
                {optionalFields.length === 1 ? '' : 's'}.
              </li>
            )}
          </ul>
        </section>
      )}

      {isComingSoon ? (
        <div
          className="rounded-lg border border-dark-600 bg-dark-800 p-4 text-sm text-gray-400"
          data-testid="details-coming-soon"
        >
          <p className="font-medium text-gray-300 mb-1">
            This connector isn't available yet.
          </p>
          {spec.deferred_reason ? (
            <p>{spec.deferred_reason}</p>
          ) : (
            <p>You can preview the planned capabilities or pick another connector.</p>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onConfigure(spec)}
          data-testid="details-configure-btn"
          className="btn btn-primary w-full"
        >
          Configure connection
        </button>
      )}

      {adminMode && (
        <div
          data-testid="details-admin-metadata"
          className="border-t border-dark-700 pt-3 text-[11px] text-gray-500 space-y-0.5"
        >
          <p className="font-semibold uppercase tracking-wide text-gray-500">
            Dev metadata
          </p>
          <p>Type: <code>{spec.type}</code></p>
          <p>Priority: {spec.priority}</p>
          <p>Integration status: {spec.status}</p>
          <p>
            Local testable:{' '}
            {spec.capabilities.local_test_available ? 'yes' : 'no'}
          </p>
        </div>
      )}
    </aside>
  );
}

// Re-export so existing imports compile against this module if needed.
export type { CredentialField };
