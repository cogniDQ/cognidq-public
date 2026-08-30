import { useState } from 'react';
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import type { EntityResolution, ResolveResponse, ResolutionCandidate } from '@/types/resolution';
import { CandidateCard } from './CandidateCard';
import ConfidenceBadge from './ConfidenceBadge';

interface DisambiguationPanelProps {
  resolution: ResolveResponse;
  onAccept: (selectedCandidates: Record<string, string>) => void;
  onCancel: () => void;
}

export function DisambiguationPanel({ resolution, onAccept, onCancel }: DisambiguationPanelProps) {
  const [subjectSelection, setSubjectSelection] = useState<string | null>(
    resolution.subject_resolution.best_candidate?.asset_id ?? null
  );
  const [objectSelection, setObjectSelection] = useState<string | null>(
    resolution.object_resolution?.best_candidate?.asset_id ?? null
  );

  const handleAccept = () => {
    const selected: Record<string, string> = {};
    if (subjectSelection) selected.subject = subjectSelection;
    if (objectSelection) selected.object = objectSelection;
    onAccept(selected);
  };

  const isBlocked = resolution.requires_disambiguation && !subjectSelection;

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-5" data-testid="disambiguation-panel">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-200">Column Resolution</h3>
        <ConfidenceBadge confidence={resolution.overall_confidence} />
      </div>

      {/* Warning banner */}
      {resolution.requires_disambiguation && (
          <div className="flex items-start gap-2 p-3 bg-dark-700 border border-yellow-800 rounded-lg" data-testid="disambiguation-warning">
          <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-yellow-400">Confirmation required</p>
            <p className="text-xs text-yellow-500 mt-0.5">
              The resolution engine could not determine the mapping with high confidence.
              Please review the candidates below and select the correct column.
            </p>
          </div>
        </div>
      )}

      {/* Subject entity */}
      <EntitySection
        label="Subject"
        entityResolution={resolution.subject_resolution}
        selectedId={subjectSelection}
        onSelect={(c) => setSubjectSelection(c.asset_id)}
      />

      {/* Object entity (if present) */}
      {resolution.object_resolution && (
        <EntitySection
          label="Object"
          entityResolution={resolution.object_resolution}
          selectedId={objectSelection}
          onSelect={(c) => setObjectSelection(c.asset_id)}
        />
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2 border-t border-dark-600">
        <button
          onClick={handleAccept}
          disabled={isBlocked}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          data-testid="accept-resolution"
        >
          <CheckCircle2 className="w-4 h-4" />
          Accept Resolution
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-300 bg-dark-700 rounded-lg hover:bg-dark-600"
          data-testid="cancel-resolution"
        >
          <XCircle className="w-4 h-4" />
          Cancel
        </button>
      </div>
    </div>
  );
}

/* ── Entity section sub-component ──────────────────────────────────────── */

interface EntitySectionProps {
  label: string;
  entityResolution: EntityResolution;
  selectedId: string | null;
  onSelect: (candidate: ResolutionCandidate) => void;
}

function EntitySection({ label, entityResolution, selectedId, onSelect }: EntitySectionProps) {
  return (
    <div data-testid={`entity-section-${label.toLowerCase()}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium text-gray-300">{label}:</span>
        <span className="text-sm text-gray-400 italic">"{entityResolution.raw_text}"</span>
        {entityResolution.requires_disambiguation && (
          <span className="text-xs bg-dark-700 text-yellow-400 px-2 py-0.5 rounded-full">
            needs review
          </span>
        )}
      </div>
      <div className="space-y-2">
        {entityResolution.candidates.length === 0 ? (
          <p className="text-sm text-gray-400 italic">No candidates found</p>
        ) : (
          entityResolution.candidates.map((c, i) => (
            <CandidateCard
              key={c.asset_id}
              candidate={c}
              isSelected={c.asset_id === selectedId}
              rank={i + 1}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </div>
  );
}
