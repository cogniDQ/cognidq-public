/**
 * F-CONN-UX — Onboarding "Recommended for you" guidance strip.
 *
 * Renders three opinionated paths (Start fast / Database / Lakehouse)
 * across the top of the catalog. Each card scrolls / activates the
 * matching customer group, helping new tenants understand where to begin.
 *
 * Spec §11 / §3.1.
 */
import { Database, FileText, Warehouse } from 'lucide-react';
import {
  CUSTOMER_GROUP_DESCRIPTION,
  CUSTOMER_GROUP_LABEL,
  CustomerGroup,
} from '../../services/connectorCatalogService';

interface RecommendedPathsProps {
  /** Available customer groups in the current registry payload. */
  availableGroups: CustomerGroup[];
  onPick: (group: CustomerGroup) => void;
  activeGroup?: CustomerGroup | null;
}

interface PathDef {
  group: CustomerGroup;
  Icon: typeof Database;
}

const PATH_ORDER: PathDef[] = [
  { group: 'start_fast', Icon: FileText },
  { group: 'connect_database', Icon: Database },
  { group: 'enterprise_lakehouse', Icon: Warehouse },
];

export default function RecommendedPaths({
  availableGroups,
  onPick,
  activeGroup,
}: RecommendedPathsProps) {
  const visible = PATH_ORDER.filter((p) => availableGroups.includes(p.group));
  if (visible.length === 0) return null;

  return (
    <section
      data-testid="recommended-paths"
      aria-label="Recommended onboarding paths"
      className="mb-6"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
        Recommended for you
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {visible.map(({ group, Icon }) => {
          const active = group === activeGroup;
          return (
            <button
              key={group}
              type="button"
              onClick={() => onPick(group)}
              data-testid={`recommended-path-${group}`}
              data-active={active}
              className={[
                'text-left p-4 rounded-xl border transition-all',
                active
                  ? 'border-primary-500 ring-2 ring-primary-500/20 bg-dark-800'
                  : 'border-dark-700 bg-dark-800 hover:border-dark-600 hover:bg-dark-700',
              ].join(' ')}
            >
              <div className="flex items-center gap-2 mb-1 text-primary-400">
                <Icon size={16} />
                <span className="text-sm font-semibold text-gray-100">
                  {CUSTOMER_GROUP_LABEL[group]}
                </span>
              </div>
              <p className="text-xs text-gray-400">
                {CUSTOMER_GROUP_DESCRIPTION[group]}
              </p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
