import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Check, Eye, Loader2 } from 'lucide-react';
import type { ResolutionCandidate } from '@/types/resolution';
import { SignalBreakdownTooltip } from './SignalBreakdownTooltip';
import { getDatasetFieldSample } from '@/services/datasetFields';

interface CandidateCardProps {
  candidate: ResolutionCandidate;
  isSelected: boolean;
  rank: number;
  onSelect: (candidate: ResolutionCandidate) => void;
}

const BAND_COLORS: Record<string, string> = {
  high: 'bg-green-100 text-green-800 border-green-200',
  medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  low: 'bg-red-100 text-red-800 border-red-200',
};

export function CandidateCard({ candidate, isSelected, rank, onSelect }: CandidateCardProps) {
  const bandClass = BAND_COLORS[candidate.confidence_band] || BAND_COLORS.low;
  const { workspace_id } = useParams<{ workspace_id: string }>();

  // E2 — table preview state
  const [previewOpen, setPreviewOpen] = useState(false);
  const [samples, setSamples] = useState<string[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const canPreview = !!(workspace_id && candidate.dataset_id && candidate.column_name);

  async function togglePreview(e: React.MouseEvent) {
    e.stopPropagation();
    if (previewOpen) {
      setPreviewOpen(false);
      return;
    }
    setPreviewOpen(true);
    if (samples !== null || previewLoading || !canPreview) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const field = await getDatasetFieldSample(
        workspace_id!,
        candidate.dataset_id!,
        candidate.column_name,
      );
      setSamples(field?.sample_values ?? []);
    } catch (err: any) {
      setPreviewError(err?.message ?? 'Failed to load sample values');
    } finally {
      setPreviewLoading(false);
    }
  }

  return (
    <div
      className={`border rounded-lg p-3 cursor-pointer transition-colors ${
        isSelected
          ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-300'
          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
      }`}
      onClick={() => onSelect(candidate)}
      data-testid={`candidate-card-${rank}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-mono w-4">#{rank}</span>
          <span className="font-medium text-sm text-gray-900" data-testid="candidate-name">
            {candidate.column_name}
          </span>
          {candidate.dataset_name && (
            <span className="text-xs text-gray-500">in {candidate.dataset_name}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full border ${bandClass}`}>
            {(candidate.overall_score * 100).toFixed(0)}%
          </span>
          {isSelected && <Check className="w-4 h-4 text-blue-600" />}
        </div>
      </div>

      {candidate.data_type && (
        <div className="mt-1 text-xs text-gray-400">Type: {candidate.data_type}</div>
      )}

      {candidate.evidence_summary.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {candidate.evidence_summary.slice(0, 4).map((e) => (
            <span key={e} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
              {e.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}

      <SignalBreakdownTooltip breakdown={candidate.signal_breakdown} />

      {canPreview && (
        <div className="mt-2">
          <button
            type="button"
            onClick={togglePreview}
            className="inline-flex items-center gap-1 text-xs text-blue-700 hover:text-blue-900"
            data-testid={`preview-toggle-${rank}`}
          >
            <Eye className="w-3 h-3" />
            {previewOpen ? 'Hide sample values' : 'Preview sample values'}
          </button>

          {previewOpen && (
            <div
              className="mt-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs"
              data-testid={`preview-panel-${rank}`}
            >
              {previewLoading ? (
                <span className="inline-flex items-center gap-1 text-gray-500">
                  <Loader2 className="w-3 h-3 animate-spin" /> Loading…
                </span>
              ) : previewError ? (
                <span className="text-red-600">{previewError}</span>
              ) : samples && samples.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {samples.slice(0, 12).map((v, i) => (
                    <span
                      key={`${v}-${i}`}
                      className="font-mono text-[11px] bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded"
                    >
                      {v === '' ? '∅ (empty)' : v}
                    </span>
                  ))}
                  {samples.length > 12 && (
                    <span className="text-[11px] text-gray-500 italic">
                      +{samples.length - 12} more…
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-gray-500 italic">
                  No sample values available for this column yet.
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

