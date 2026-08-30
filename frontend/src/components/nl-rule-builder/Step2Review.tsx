import { Loader2 } from 'lucide-react'
import type { ParseRuleResponse, ClarificationTurn } from '@/types/nlRuleBuilder'
import type { ResolveResponse } from '@/types/resolution'
import ParseResultPanel from './ParseResultPanel'
import WarningsBanner from './WarningsBanner'
import DecompositionSummaryPanel from './DecompositionSummaryPanel'
import ExplainabilitySection from './ExplainabilitySection'
import ClarificationPanel from './ClarificationPanel'
import ClarificationHistoryPanel from './ClarificationHistoryPanel'
import { DisambiguationPanel } from './DisambiguationPanel'
import SIRFieldEditor from './SIRFieldEditor'
import ObligationsBreakdownPanel from './ObligationsBreakdownPanel'

interface Step2ReviewProps {
  parseResult: ParseRuleResponse
  resolution: ResolveResponse | null
  onClarify: (answers: Record<string, string>) => void
  isClarifying: boolean
  onAcceptResolution: (selectedCandidates: Record<string, string>) => void
  onCancelResolution: () => void
  isResolving: boolean
  onContinue: () => void
  onBack: () => void
  onParseResultChange?: (next: ParseRuleResponse) => void
  /** F1 — prior clarification Q/A turns (oldest first) */
  clarificationTurns?: ClarificationTurn[]
}

export default function Step2Review({
  parseResult,
  resolution,
  onClarify,
  isClarifying,
  onAcceptResolution,
  onCancelResolution,
  isResolving,
  onContinue,
  onBack,
  onParseResultChange,
  clarificationTurns = [],
}: Step2ReviewProps) {
  const needsClarification = parseResult.status === 'needs_clarification'
  const needsDisambiguation =
    resolution?.requires_disambiguation === true ||
    parseResult.parsed_rule?.requires_disambiguation === true

  // Block "Continue" while clarification or disambiguation is unresolved
  const canContinue =
    parseResult.status === 'parsed' &&
    !needsClarification &&
    !needsDisambiguation

  const warnings = parseResult.parsed_rule?.parse_warnings ?? []
  const explainabilityItems = parseResult.explainability ?? []
  const decompositionSummary = parseResult.decomposition_summary ?? null
  const questions = parseResult.clarifying_questions ?? []

  return (
    <div className="space-y-4" data-testid="step2-review">
      {/* Parse warnings */}
      {warnings.length > 0 && <WarningsBanner warnings={warnings} />}

      {/* Main parse result */}
      <ParseResultPanel
        result={parseResult}
        isPending={false}
        error={null}
        onClarify={onClarify}
        isClarifying={isClarifying}
      />

      {/* E4 — direct field editor */}
      {parseResult.parsed_rule && onParseResultChange && (
        <SIRFieldEditor
          parseResult={parseResult}
          onChange={onParseResultChange}
        />
      )}

      {/* Explainability */}
      {explainabilityItems.length > 0 && (
        <ExplainabilitySection
          items={explainabilityItems}
          trustSummary={parseResult.trust_summary}
        />
      )}

      {/* Decomposition summary */}
      {decompositionSummary && decompositionSummary.count > 1 && (
        <DecompositionSummaryPanel summary={decompositionSummary} />
      )}

      {/* F3 — per-obligation breakdown */}
      {parseResult.parsed_rule && (
        <ObligationsBreakdownPanel parsedRule={parseResult.parsed_rule} />
      )}

      {/* F1 — prior clarification turns */}
      {clarificationTurns.length > 0 && (
        <ClarificationHistoryPanel turns={clarificationTurns} />
      )}

      {/* Inline clarification Q&A */}
      {needsClarification && questions.length > 0 && (
        <ClarificationPanel
          questions={questions}
          context={parseResult.clarification_context}
          onSubmit={onClarify}
          isSubmitting={isClarifying}
        />
      )}

      {/* Disambiguation */}
      {resolution && (
        <DisambiguationPanel
          resolution={resolution}
          onAccept={onAcceptResolution}
          onCancel={onCancelResolution}
        />
      )}

      {/* Navigation */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={onBack}
          className="btn btn-secondary"
          data-testid="step2-back-btn"
        >
          Back
        </button>

        {canContinue && (
          <button
            onClick={onContinue}
            className="btn btn-primary"
            data-testid="step2-continue-btn"
          >
            {isResolving ? (
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
            ) : null}
            Continue to Confirm
          </button>
        )}
      </div>
    </div>
  )
}
