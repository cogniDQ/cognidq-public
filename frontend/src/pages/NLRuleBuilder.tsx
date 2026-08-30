import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { parseRule, resolveRule, listParses } from '@/services/nlRuleBuilderService'
import { createProposal } from '@/services/proposalService'
import type { ScheduleConfig } from '@/components/nl-rule-builder/ParseResultModal'
import type {
  NLRuleDraft,
  ParseRuleResponse,
  ParseRuleRequest,
  RecentParseEntry,
  ClarificationTurn,
} from '@/types/nlRuleBuilder'
import type { ResolveResponse } from '@/types/resolution'
import StepIndicator from '@/components/nl-rule-builder/StepIndicator'
import Step1Input from '@/components/nl-rule-builder/Step1Input'
import Step2Review from '@/components/nl-rule-builder/Step2Review'
import Step3Confirm from '@/components/nl-rule-builder/Step3Confirm'
import { api } from '@/services/api'
import { useTenantScopedPath } from '@/hooks/useTenantScopedPath'

const DRAFT_KEY = (wsId: string) => `nl-rule-draft-${wsId}`
const HISTORY_KEY = (wsId: string) => `nl-rule-history-${wsId}`
const MAX_HISTORY = 5

function extractErrorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) {
    return detail.map((e: any) => e?.msg || JSON.stringify(e)).join('; ')
  }
  if (typeof detail === 'string') return detail
  return error?.message || fallback
}

function loadDraft(wsId: string): NLRuleDraft {
  try {
    const stored = localStorage.getItem(DRAFT_KEY(wsId))
    if (stored) return JSON.parse(stored)
  } catch { /* ignore corrupt data */ }
  return { rule_text: '', dataset_id: '', domain: '', severity: 'medium', tags: [], use_context: false }
}

function loadHistory(wsId: string): RecentParseEntry[] {
  try {
    const stored = localStorage.getItem(HISTORY_KEY(wsId))
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return []
}

export default function NLRuleBuilder() {
  const { workspace_id } = useParams<{ workspace_id: string }>()
  const wsId = workspace_id || ''
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { wsPath } = useTenantScopedPath()
  const [searchParams, setSearchParams] = useSearchParams()

  // --- Step state ---
  const [step, setStep] = useState<1 | 2 | 3>(1)

  // --- Draft + history ---
  const [draft, setDraft] = useState<NLRuleDraft>(() => loadDraft(wsId))
  const [parseResult, setParseResult] = useState<ParseRuleResponse | null>(null)
  const [resolution, setResolution] = useState<ResolveResponse | null>(null)
  const [history, setHistory] = useState<RecentParseEntry[]>(() => loadHistory(wsId))
  // F1 — multi-turn clarification history (in-memory; oldest first)
  const [clarificationTurns, setClarificationTurns] = useState<ClarificationTurn[]>([])
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Fetch datasets
  const { data: datasets = [] } = useQuery({
    queryKey: ['datasets', wsId],
    queryFn: async () => {
      const { data } = await api.get(`/workspaces/${wsId}/datasets`)
      const raw: any[] = data.items || data.datasets || []
      return raw.map((ds: any) => ({
        id: ds.dataset_id || ds.id,
        name: ds.dataset_name || ds.name,
        dataset_id: ds.dataset_id || ds.id,
        data_source_name: ds.data_source_name || null,
      }))
    },
    enabled: !!wsId,
    staleTime: 60_000,
  })

  // Draft autosave (2s debounce) — active only on Step 1
  useEffect(() => {
    if (step !== 1) return
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => {
      localStorage.setItem(DRAFT_KEY(wsId), JSON.stringify(draft))
    }, 2000)
    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    }
  }, [draft, wsId, step])

  // F2 — hydrate draft from URL params (?dataset_id=…&rule_text=…) so deep
  // links from the dataset detail page open the builder pre-seeded with
  // the right context. Runs once after datasets load. Strips the params
  // from the URL afterward to avoid re-applying on draft autosave.
  const hydratedRef = useRef(false)
  useEffect(() => {
    if (hydratedRef.current) return
    const qsDatasetId = searchParams.get('dataset_id')
    const qsRuleText = searchParams.get('rule_text')
    if (!qsDatasetId && !qsRuleText) {
      hydratedRef.current = true
      return
    }
    // Wait for datasets so we can validate the id before applying it.
    if (qsDatasetId && datasets.length === 0) return
    setDraft((prev) => {
      const next = { ...prev }
      if (qsDatasetId && datasets.some((d) => d.dataset_id === qsDatasetId)) {
        next.dataset_id = qsDatasetId
        next.use_context = true
      }
      if (qsRuleText && !prev.rule_text) {
        next.rule_text = qsRuleText.slice(0, 500)
      }
      return next
    })
    hydratedRef.current = true
    // Strip the consumed params; preserve any others the page may add later.
    const cleared = new URLSearchParams(searchParams)
    cleared.delete('dataset_id')
    cleared.delete('rule_text')
    setSearchParams(cleared, { replace: true })
  }, [datasets, searchParams, setSearchParams])

  // Parse mutation
  const parseMutation = useMutation({
    mutationFn: (payload: ParseRuleRequest) => parseRule(wsId, payload),
    onSuccess: (data) => {
      if (data.status === 'needs_clarification') {
        setParseResult(data)
        setResolution(null)
        setStep(2)
        if (data.clarification_context) {
          toast('Your answers need adjustment. See details below.', { icon: '🔄' })
        } else {
          toast('The parser needs more information. Please answer the questions below.', { icon: '❓' })
        }
        return
      }
      if (data.status !== 'parsed' || !data.parsed_rule) {
        const msg = data.reason || data.suggestions?.[0] || 'Could not interpret rule'
        toast.error(msg)
        setParseResult(data)
        setStep(2)
        return
      }
      setParseResult(data)
      setResolution(null)
      setStep(2)
      // Add to history
      const entry: RecentParseEntry = {
        rule_text: draft.rule_text,
        confidence: data.parsed_rule.confidence,
        rule_type: data.parsed_rule.rule_type,
        timestamp: new Date().toISOString(),
      }
      const updated = [entry, ...history].slice(0, MAX_HISTORY)
      setHistory(updated)
      localStorage.setItem(HISTORY_KEY(wsId), JSON.stringify(updated))
      toast.success('Rule parsed — review the result below')
    },
    onError: (error: any) => {
      toast.error(extractErrorMessage(error, 'Failed to parse rule'))
    },
  })

  // Resolve mutation
  const resolveMutation = useMutation({
    mutationFn: (payload: { parsed_rule: Record<string, unknown>; dataset_context?: string; domain_context?: string; selected_candidates?: Record<string, string> }) =>
      resolveRule(wsId, payload),
    onSuccess: (data) => {
      setResolution(data)
    },
    onError: (error: any) => {
      toast.error(extractErrorMessage(error, 'Failed to resolve columns'))
    },
  })

  // Fetch saved parses
  const { data: savedParses } = useQuery({
    queryKey: ['parses', wsId],
    queryFn: () => listParses(wsId, 1, MAX_HISTORY),
    enabled: !!wsId,
    staleTime: 30_000,
  })

  // Submit-as-proposal mutation
  const submitProposalMutation = useMutation({
    mutationFn: (params: { datasetId?: string; schedule?: ScheduleConfig }) =>
      createProposal(
        wsId,
        draft.rule_text.trim(),
        params.datasetId || draft.dataset_id || undefined,
        draft.domain || undefined,
      ),
    onSuccess: () => {
      toast.success('Proposal submitted — review and confirm in Rules → Proposals')
      queryClient.invalidateQueries({ queryKey: ['proposals', wsId] })
      navigate(wsPath(wsId, '/rules?tab=proposals'))
    },
    onError: (error: any) => {
      toast.error(extractErrorMessage(error, 'Failed to submit proposal'))
    },
  })

  // --- Handlers ---
  const handleInterpret = useCallback(() => {
    const text = draft.rule_text.trim()
    if (!text) return
    // F1 — fresh interpretation resets the clarification history
    setClarificationTurns([])
    const payload: ParseRuleRequest = {
      rule_text: text,
      dataset_id: draft.dataset_id || undefined,
      domain: draft.domain || undefined,
      severity: draft.severity,
      tags: draft.tags.length > 0 ? draft.tags : undefined,
    }
    parseMutation.mutate(payload)
  }, [draft, parseMutation])

  const handleClarify = useCallback((answers: Record<string, string>) => {
    const text = draft.rule_text.trim()
    if (!text) return
    // F1 — record this Q/A pair into the clarification history before re-parsing
    const askedQuestions = parseResult?.clarifying_questions ?? []
    const now = new Date().toISOString()
    const newTurns: ClarificationTurn[] = Object.entries(answers)
      .filter(([, v]) => v !== undefined && v !== null && String(v).trim() !== '')
      .map(([field, answer]) => ({
        field,
        question:
          askedQuestions.find((q) => q.field === field)?.question ??
          `Answer for ${field}`,
        answer: String(answer),
        answered_at: now,
      }))
    const nextTurns = [...clarificationTurns, ...newTurns]
    setClarificationTurns(nextTurns)
    const payload: ParseRuleRequest = {
      rule_text: text,
      dataset_id: draft.dataset_id || undefined,
      domain: draft.domain || undefined,
      severity: draft.severity,
      tags: draft.tags.length > 0 ? draft.tags : undefined,
      clarification_answers: answers,
      clarification_history: nextTurns.length > 0 ? nextTurns : undefined,
    }
    parseMutation.mutate(payload)
  }, [draft, parseMutation, parseResult, clarificationTurns])

  const handleAcceptResolution = useCallback((selectedCandidates: Record<string, string>) => {
    if (!parseResult?.parsed_rule) return
    resolveMutation.mutate({
      parsed_rule: parseResult.parsed_rule as unknown as Record<string, unknown>,
      dataset_context: draft.dataset_id || undefined,
      domain_context: draft.domain || undefined,
      selected_candidates: selectedCandidates,
    })
  }, [parseResult, draft, resolveMutation])

  const handleCancelResolution = useCallback(() => {
    setResolution(null)
  }, [])

  const handleSubmitProposal = useCallback((datasetId?: string, schedule?: ScheduleConfig) => {
    submitProposalMutation.mutate({ datasetId, schedule })
  }, [submitProposalMutation])

  const handleClear = useCallback(() => {
    setDraft({ rule_text: '', dataset_id: '', domain: '', severity: 'medium', tags: [], use_context: false })
    setParseResult(null)
    setResolution(null)
    setClarificationTurns([])
    setStep(1)
    localStorage.removeItem(DRAFT_KEY(wsId))
  }, [wsId])

  const handleGoBackToStep1 = useCallback(() => {
    setParseResult(null)
    setResolution(null)
    setClarificationTurns([])
    setStep(1)
  }, [])

  const handleGoBackToStep2 = useCallback(() => {
    setStep(2)
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-100 flex items-center gap-2">
            <Sparkles className="w-7 h-7 text-primary-400" />
            NL Rule Builder
          </h1>
          <p className="text-gray-400 mt-1">
            Write your business rule in plain English and we'll interpret it
          </p>
        </div>
        <button
          onClick={handleClear}
          className="btn btn-secondary flex items-center gap-2 text-sm"
        >
          <Trash2 className="w-4 h-4" />
          Clear
        </button>
      </div>

      {/* Step indicator */}
      <StepIndicator currentStep={step} />

      {/* Step content */}
      {step === 1 && (
        <Step1Input
          draft={draft}
          onDraftChange={(partial) => setDraft((prev) => ({ ...prev, ...partial }))}
          onParse={handleInterpret}
          isParseLoading={parseMutation.isPending}
          parseError={parseMutation.isError ? (parseMutation.error as Error) : null}
          datasets={datasets}
          history={history}
          savedParses={savedParses}
        />
      )}

      {step === 2 && parseResult && (
        <div data-testid="parse-result-panel">
        <Step2Review
          parseResult={parseResult}
          resolution={resolution}
          onClarify={handleClarify}
          isClarifying={parseMutation.isPending}
          onAcceptResolution={handleAcceptResolution}
          onCancelResolution={handleCancelResolution}
          isResolving={resolveMutation.isPending}
          onContinue={() => setStep(3)}
          onBack={handleGoBackToStep1}
          onParseResultChange={setParseResult}
          clarificationTurns={clarificationTurns}
        />
        </div>
      )}


      {step === 3 && parseResult && (
        <Step3Confirm
          parseResult={parseResult}
          draft={draft}
          onDraftChange={(partial) => setDraft((prev) => ({ ...prev, ...partial }))}
          datasets={datasets}
          onSubmitProposal={handleSubmitProposal}
          isSubmitting={submitProposalMutation.isPending}
          onBack={handleGoBackToStep2}
        />
      )}
    </div>
  )
}
