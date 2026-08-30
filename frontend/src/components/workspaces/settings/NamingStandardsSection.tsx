/**
 * NamingStandardsSection — displays and allows editing naming constraints for
 * datasets and rules using the reusable DomainConstraintForm.
 */
import type { NamingStandards, NamingConstraint } from '../../../types/workspaceSettings';
import DomainConstraintForm from './DomainConstraintForm';

interface Props {
  value: NamingStandards;
  canEdit: boolean;
  onSaveDatasetsConstraint: (update: NamingConstraint) => Promise<void>;
  onSaveRulesConstraint: (update: NamingConstraint) => Promise<void>;
}

export default function NamingStandardsSection({
  value,
  canEdit,
  onSaveDatasetsConstraint,
  onSaveRulesConstraint,
}: Props) {
  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="naming-standards-section"
    >
      <h2 className="text-lg font-semibold text-white mb-4">Naming Standards</h2>
      <div className="space-y-4">
        <DomainConstraintForm
          label="Datasets"
          value={value.datasets}
          canEdit={canEdit}
          testidPrefix="datasets"
          onSave={onSaveDatasetsConstraint}
        />
        <DomainConstraintForm
          label="Rules"
          value={value.rules}
          canEdit={canEdit}
          testidPrefix="rules"
          onSave={onSaveRulesConstraint}
        />
      </div>
    </section>
  );
}
