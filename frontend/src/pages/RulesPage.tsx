import { useState, useCallback, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Search,
  Filter,
  MoreHorizontal,
  Edit,
  Trash2,
  Power,
  PowerOff,
  GitBranch,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  BookOpen,
  Settings,
  Columns,
  Database,
  User,
  Pencil,
  Save,
} from 'lucide-react'
import { api } from '@/services/api'
import toast from 'react-hot-toast'
import {
  listRules,
  createRule,
  updateRule,
  deleteRule,
  executeRule,
  buildFlowFromRules,
  type RuleResponse,
  type CreateRuleRequest,
  type UpdateRuleRequest,
} from '@/services/ruleService'
import {
  listProposals,
  confirmProposal,
  rejectProposal,
  type Proposal,
} from '@/services/proposalService'
import RuleCreateModal from '@/components/rules/RuleCreateModal'
import RuleExecutionsModal from '@/components/rules/RuleExecutionsModal'
import { useTenantScopedPath } from '@/hooks/useTenantScopedPath'

const CATEGORY_COLORS: Record<string, string> = {
  completeness: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  validity: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  conformity: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  uniqueness: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  consistency: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  accuracy: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  timeliness: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
  statistical: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
  reconciliation: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
}

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  active: { icon: CheckCircle2, color: 'text-green-500', label: 'Active' },
  draft: { icon: Clock, color: 'text-gray-400', label: 'Draft' },
  inactive: { icon: XCircle, color: 'text-red-400', label: 'Inactive' },
  archived: { icon: AlertTriangle, color: 'text-yellow-500', label: 'Archived' },
}

const PROPOSAL_STATUS_STYLES: Record<string, { icon: typeof Clock; color: string; bg: string; label: string }> = {
  pending:   { icon: Clock,        color: 'text-yellow-400', bg: 'bg-yellow-500/20', label: 'Pending' },
  confirmed: { icon: CheckCircle2, color: 'text-green-400',  bg: 'bg-green-500/20',  label: 'Confirmed' },
  adjusted:  { icon: CheckCircle2, color: 'text-blue-400',   bg: 'bg-blue-500/20',   label: 'Adjusted' },
  rejected:  { icon: XCircle,      color: 'text-red-400',    bg: 'bg-red-500/20',    label: 'Rejected' },
}

type TabId = 'rules' | 'proposals'

export default function RulesPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>()
  const wsId = workspace_id || ''
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { wsPath } = useTenantScopedPath()

  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [selectedRules, setSelectedRules] = useState<Set<string>>(new Set())
  const [editingRule, setEditingRule] = useState<RuleResponse | null>(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [actionMenuId, setActionMenuId] = useState<string | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') === 'proposals' ? 'proposals' : 'rules')
  )
  const [proposalStatusFilter, setProposalStatusFilter] = useState<string>('')
  const [expandedProposal, setExpandedProposal] = useState<string | null>(null)

  // F4 — keep tab state and URL in sync. Reads on mount + back/forward,
  // and writes back when the user clicks a tab.
  useEffect(() => {
    const fromUrl = searchParams.get('tab')
    if (fromUrl === 'proposals' && activeTab !== 'proposals') {
      setActiveTab('proposals')
    } else if ((fromUrl === null || fromUrl === 'rules') && activeTab !== 'rules') {
      // Don't fight the executions deep-link path (handled below)
      if (fromUrl !== 'executions') setActiveTab('rules')
    }
     
  }, [searchParams])

  const changeTab = useCallback((next: TabId) => {
    setActiveTab(next)
    const params = new URLSearchParams(searchParams)
    if (next === 'rules') {
      params.delete('tab')
    } else {
      params.set('tab', next)
    }
    setSearchParams(params, { replace: true })
  }, [searchParams, setSearchParams])

  // F7 — surface execution history when deep-linked from the dataset detail
  // page's Quality panel (`?rule=<id>&tab=executions`). The modal closes by
  // stripping those params, leaving the rules list intact.
  const deepLinkRuleId = searchParams.get('rule') ?? null
  const showExecutionsModal =
    !!deepLinkRuleId && searchParams.get('tab') === 'executions'
  const closeExecutionsModal = useCallback(() => {
    const next = new URLSearchParams(searchParams)
    next.delete('rule')
    next.delete('tab')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  // Fetch datasets for proposal editor
  const { data: datasets = [] } = useQuery({
    queryKey: ['datasets', wsId],
    queryFn: async () => {
      const { data } = await api.get(`/workspaces/${wsId}/datasets`)
      const raw: any[] = data.items || data.datasets || []
      return raw.map((ds: any) => ({
        id: ds.dataset_id || ds.id,
        name: `${ds.data_source_name ? ds.data_source_name + '.' : ''}${ds.dataset_name || ds.name}`,
      }))
    },
    enabled: !!wsId,
    staleTime: 60_000,
  })

  // Fetch rules
  const { data: rules = [], isLoading, error } = useQuery({
    queryKey: ['rules', wsId, search, categoryFilter, statusFilter],
    queryFn: () =>
      listRules(wsId, {
        search: search || undefined,
        category: categoryFilter || undefined,
        status: statusFilter || undefined,
      }),
    enabled: !!wsId,
  })

  // Open edit modal when deep-linked via ``?rule=<id>`` (without
  // ``tab=executions``). Used by the dataset-detail Quality panel's
  // "Open rule →" link so the rule loads in-place rather than just
  // landing on the rules list with no indication of which rule was meant.
  useEffect(() => {
    if (!deepLinkRuleId || showExecutionsModal) return
    if (showEditModal) return
    const target = rules.find((r) => r.id === deepLinkRuleId)
    if (target) {
      setEditingRule(target)
      setShowEditModal(true)
    }
  }, [deepLinkRuleId, showExecutionsModal, showEditModal, rules])

  // Fetch proposals
  const { data: proposalsData, isLoading: proposalsLoading } = useQuery({
    queryKey: ['proposals', wsId, proposalStatusFilter],
    queryFn: () => listProposals(wsId, { status: proposalStatusFilter || undefined, limit: 100 }),
    enabled: !!wsId && activeTab === 'proposals',
    staleTime: 15_000,
  })
  const proposals = proposalsData?.items ?? []
  const proposalTotal = proposalsData?.total ?? 0

  // Confirm proposal mutation
  const confirmMut = useMutation({
    mutationFn: ({ id, adjustments }: { id: string; adjustments?: ProposalAdjustment[] }) =>
      confirmProposal(wsId, id, adjustments || []),
    onSuccess: () => {
      toast.success('Proposal confirmed — rule created')
      queryClient.invalidateQueries({ queryKey: ['proposals', wsId] })
      queryClient.invalidateQueries({ queryKey: ['rules', wsId] })
      changeTab('rules')
    },
    onError: () => toast.error('Failed to confirm proposal'),
  })

  // Reject proposal mutation
  const rejectMut = useMutation({
    mutationFn: (id: string) => rejectProposal(wsId, id),
    onSuccess: () => {
      toast.success('Proposal rejected')
      queryClient.invalidateQueries({ queryKey: ['proposals', wsId] })
    },
    onError: () => toast.error('Failed to reject proposal'),
  })

  // Toggle active mutation
  const toggleActiveMutation = useMutation({
    mutationFn: ({ ruleId, isActive }: { ruleId: string; isActive: boolean }) =>
      updateRule(wsId, ruleId, { is_active: isActive, status: isActive ? 'active' : 'inactive' }),
    onSuccess: (_, { isActive }) => {
      toast.success(isActive ? 'Rule activated' : 'Rule deactivated')
      queryClient.invalidateQueries({ queryKey: ['rules', wsId] })
    },
    onError: () => toast.error('Failed to update rule'),
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (ruleId: string) => deleteRule(wsId, ruleId),
    onSuccess: () => {
      toast.success('Rule deleted')
      queryClient.invalidateQueries({ queryKey: ['rules', wsId] })
    },
    onError: () => toast.error('Failed to delete rule'),
  })

  // Build flow from selected rules
  const buildFlowMutation = useMutation({
    mutationFn: (ruleIds: string[]) => buildFlowFromRules(wsId, ruleIds),
    onSuccess: (data) => {
      toast.success(`Flow "${data.flow_name}" created`)
      navigate(wsId ? wsPath(wsId, '/flows') : '/hub/flows')
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Failed to build flow from rules')
    },
  })

  // Execute single rule
  const executeMutation = useMutation({
    mutationFn: (ruleId: string) => executeRule(wsId, ruleId),
    onSuccess: (exec) => {
      toast.success(`Execution started (${exec.id.slice(0, 8)}…)`)
      queryClient.invalidateQueries({ queryKey: ['rules', wsId] })
    },
    onError: (err: any) =>
      toast.error(err?.response?.data?.detail ?? 'Failed to execute rule'),
  })

  const handleEdit = useCallback((rule: RuleResponse) => {
    setEditingRule(rule)
    setShowEditModal(true)
    setActionMenuId(null)
  }, [])

  const handleDelete = useCallback(
    (ruleId: string) => {
      if (window.confirm('Are you sure you want to delete this rule?')) {
        deleteMutation.mutate(ruleId)
      }
      setActionMenuId(null)
    },
    [deleteMutation]
  )

  const handleToggleActive = useCallback(
    (rule: RuleResponse) => {
      toggleActiveMutation.mutate({ ruleId: rule.id, isActive: !rule.is_active })
      setActionMenuId(null)
    },
    [toggleActiveMutation]
  )

  const handleBuildFlow = useCallback(() => {
    if (selectedRules.size === 0) {
      toast.error('Select at least one rule to build a flow')
      return
    }
    const selectedRuleObjects = rules.filter((r) => selectedRules.has(r.id))
    const missingDataset = selectedRuleObjects.filter((r) => !r.target_table)
    if (missingDataset.length > 0) {
      toast.error(
        `${missingDataset.length} rule(s) have no dataset configured: ${missingDataset.map((r) => r.name).join(', ')}. Edit them first.`
      )
      return
    }
    buildFlowMutation.mutate(Array.from(selectedRules))
  }, [selectedRules, rules, buildFlowMutation])

  const handleSelectAll = useCallback(() => {
    if (selectedRules.size === rules.length) {
      setSelectedRules(new Set())
    } else {
      setSelectedRules(new Set(rules.map((r) => r.id)))
    }
  }, [rules, selectedRules])

  const toggleSelect = useCallback((ruleId: string) => {
    setSelectedRules((prev) => {
      const next = new Set(prev)
      if (next.has(ruleId)) next.delete(ruleId)
      else next.add(ruleId)
      return next
    })
  }, [])

  const handleSaveEdit = useCallback(
    async (ruleId: string, updates: UpdateRuleRequest) => {
      try {
        await updateRule(wsId, ruleId, updates)
        toast.success('Rule updated')
        setShowEditModal(false)
        setEditingRule(null)
        queryClient.invalidateQueries({ queryKey: ['rules', wsId] })
      } catch {
        toast.error('Failed to update rule')
      }
    },
    [wsId, queryClient]
  )

  const handleCreateRule = useCallback(
    async (payload: CreateRuleRequest) => {
      // Errors bubble up so the modal can surface the backend message.
      await createRule(wsId, payload)
      toast.success('Rule created')
      setShowCreateModal(false)
      queryClient.invalidateQueries({ queryKey: ['rules', wsId] })
    },
    [wsId, queryClient]
  )

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Rules</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage data quality rules and review proposals
          </p>
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'rules' && selectedRules.size > 0 && (
            <button
              onClick={handleBuildFlow}
              disabled={buildFlowMutation.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              <GitBranch className="w-4 h-4" />
              Build Flow ({selectedRules.size})
            </button>
          )}
          <button
            onClick={() => navigate(`/hub/nl-rule-builder`)}
            data-testid="rules-nl-builder-btn"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            title="Generate rules from natural language"
          >
            <Sparkles className="w-4 h-4" />
            NL Builder
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            data-testid="rules-new-rule-btn"
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" />
            New Rule
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex space-x-8" aria-label="Tabs">
          <button
            onClick={() => changeTab('rules')}
            className={`py-3 px-1 border-b-2 text-sm font-medium ${
              activeTab === 'rules'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
          >
            Confirmed Rules
          </button>
          <button
            onClick={() => changeTab('proposals')}
            className={`py-3 px-1 border-b-2 text-sm font-medium ${
              activeTab === 'proposals'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
          >
            Proposals
            {proposalTotal > 0 && (
              <span className="ml-2 inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">
                {proposalTotal}
              </span>
            )}
          </button>
        </nav>
      </div>

      {/* ── Rules Tab ─────────────────────────────────────────────────── */}
      {activeTab === 'rules' && (
        <>
          {/* Filters */}
          <div className="flex items-center gap-4 flex-wrap">
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search rules..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-gray-400" />
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              >
                <option value="">All Categories</option>
                <option value="completeness">Completeness</option>
                <option value="validity">Validity</option>
                <option value="conformity">Conformity</option>
                <option value="uniqueness">Uniqueness</option>
                <option value="consistency">Consistency</option>
                <option value="accuracy">Accuracy</option>
                <option value="timeliness">Timeliness</option>
                <option value="statistical">Statistical</option>
                <option value="reconciliation">Reconciliation</option>
              </select>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="draft">Draft</option>
                <option value="inactive">Inactive</option>
                <option value="archived">Archived</option>
              </select>
            </div>
          </div>

          {/* Rules Table */}
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-red-500">Failed to load rules</div>
          ) : rules.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400 text-lg">No rules found</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
                Create one manually or generate from natural language
              </p>
              <div className="mt-4 inline-flex items-center gap-2">
                <button
                  onClick={() => setShowCreateModal(true)}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  <Plus className="w-4 h-4" />
                  Create Rule
                </button>
                <button
                  onClick={() => navigate(`/hub/nl-rule-builder`)}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  <Sparkles className="w-4 h-4" />
                  NL Builder
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
                    <th className="px-4 py-3 text-left">
                      <input
                        type="checkbox"
                        checked={selectedRules.size === rules.length && rules.length > 0}
                        onChange={handleSelectAll}
                        className="rounded border-gray-300"
                      />
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Type
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Target
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Updated
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {rules.map((rule) => {
                    const statusCfg = STATUS_CONFIG[rule.status] || STATUS_CONFIG.draft
                    const StatusIcon = statusCfg.icon
                    return (
                      <tr
                        key={rule.id}
                        data-testid={`rule-row-${rule.id}`}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            checked={selectedRules.has(rule.id)}
                            onChange={() => toggleSelect(rule.id)}
                            className="rounded border-gray-300"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => handleEdit(rule)}
                            data-testid={`rule-name-btn-${rule.id}`}
                            className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline truncate max-w-xs text-left"
                            title="Open rule to view/edit"
                          >
                            {rule.name}
                          </button>
                          {rule.description && (
                            <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-xs">
                              {rule.description}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${CATEGORY_COLORS[rule.category] || 'bg-gray-100 text-gray-800'}`}
                          >
                            {rule.category}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {rule.rule_type || '-'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5">
                            <StatusIcon className={`w-4 h-4 ${statusCfg.color}`} />
                            <span className="text-sm text-gray-700 dark:text-gray-300">
                              {statusCfg.label}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          {rule.target_table ? (
                            <>
                              {rule.target_table}
                              {rule.target_columns?.length
                                ? ` (${rule.target_columns.join(', ')})`
                                : ''}
                            </>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-amber-400" title="No dataset configured — rule cannot run in a flow">
                              <span>⚠</span>
                              <span>No dataset</span>
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                          {new Date(rule.updated_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-right relative">
                          <div className="inline-flex items-center gap-2 justify-end">
                            <button
                              type="button"
                              onClick={() => executeMutation.mutate(rule.id)}
                              disabled={executeMutation.isPending}
                              data-testid={`rule-run-btn-${rule.id}`}
                              className="px-2.5 py-1 text-xs rounded-md border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
                            >
                              {executeMutation.isPending && executeMutation.variables === rule.id
                                ? 'Running…'
                                : 'Run'}
                            </button>
                            <button
                              onClick={() =>
                                setActionMenuId(actionMenuId === rule.id ? null : rule.id)
                              }
                              data-testid={`rule-actions-btn-${rule.id}`}
                              className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
                            >
                              <MoreHorizontal className="w-4 h-4 text-gray-500" />
                            </button>
                          </div>
                          {actionMenuId === rule.id && (
                            <div className="absolute right-4 top-10 z-50 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg py-1">
                              <button
                                onClick={() => handleEdit(rule)}
                                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                              >
                                <Edit className="w-4 h-4" />
                                Edit Rule
                              </button>
                              <button
                                onClick={() => handleToggleActive(rule)}
                                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                              >
                                {rule.is_active ? (
                                  <>
                                    <PowerOff className="w-4 h-4" />
                                    Deactivate
                                  </>
                                ) : (
                                  <>
                                    <Power className="w-4 h-4" />
                                    Activate
                                  </>
                                )}
                              </button>
                              <button
                                onClick={() => {
                                  buildFlowMutation.mutate([rule.id])
                                  setActionMenuId(null)
                                }}
                                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                              >
                                <GitBranch className="w-4 h-4" />
                                Build Flow
                              </button>
                              <hr className="my-1 border-gray-200 dark:border-gray-700" />
                              <button
                                onClick={() => handleDelete(rule.id)}
                                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                              >
                                <Trash2 className="w-4 h-4" />
                                Delete Rule
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Proposals Tab ─────────────────────────────────────────────── */}
      {activeTab === 'proposals' && (
        <>
          {/* Proposal status filters */}
          <div className="flex items-center gap-2">
            {['', 'pending', 'confirmed', 'rejected'].map((s) => (
              <button
                key={s}
                onClick={() => setProposalStatusFilter(s)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  proposalStatusFilter === s
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
                }`}
              >
                {s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All'}
              </button>
            ))}
          </div>

          {/* Proposal cards */}
          {proposalsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : proposals.length === 0 ? (
            <div className="text-center py-12">
              <Sparkles className="w-16 h-16 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
              <p className="text-gray-500 dark:text-gray-400 text-lg">No proposals found</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
                Use the NL Rule Builder to create rules — proposals are generated automatically
              </p>
              <button
                onClick={() => navigate(`/hub/nl-rule-builder`)}
                className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                <Sparkles className="w-4 h-4" />
                Open NL Rule Builder
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {proposals.map((proposal) => (
                <ProposalCard
                  key={proposal.proposal_id}
                  proposal={proposal}
                  datasets={datasets}
                  expanded={expandedProposal === proposal.proposal_id}
                  onToggleExpand={() =>
                    setExpandedProposal(
                      expandedProposal === proposal.proposal_id ? null : proposal.proposal_id
                    )
                  }
                  onConfirm={(id, adjustments) => confirmMut.mutate({ id, adjustments })}
                  onReject={(id) => rejectMut.mutate(id)}
                />
              ))}
              <div className="text-sm text-gray-500 dark:text-gray-400 text-center">
                Showing {proposals.length} of {proposalTotal} proposals
              </div>
            </div>
          )}
        </>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <RuleCreateModal
          workspaceId={wsId}
          onCreate={handleCreateRule}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {/* Edit Modal — reuses the schema-driven create form with prefilled values */}
      {showEditModal && editingRule && (
        <RuleCreateModal
          workspaceId={wsId}
          rule={editingRule}
          onUpdate={handleSaveEdit}
          onClose={() => {
            setShowEditModal(false)
            setEditingRule(null)
            // Clear ``?rule=`` deep link so reopening the page does not
            // immediately re-trigger the modal effect.
            if (searchParams.get('rule')) {
              const next = new URLSearchParams(searchParams)
              next.delete('rule')
              setSearchParams(next, { replace: true })
            }
          }}
        />
      )}

      {/* F7 — Executions modal opened via deep link from the dataset page */}
      {showExecutionsModal && deepLinkRuleId && (
        <RuleExecutionsModal
          workspaceId={wsId}
          ruleId={deepLinkRuleId}
          ruleName={rules.find((r) => r.id === deepLinkRuleId)?.name}
          onClose={closeExecutionsModal}
        />
      )}
    </div>
  )
}

// ── Proposal Card Component ──────────────────────────────────────────────────

function ConfidenceBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100)
  const color = pct >= 90 ? 'bg-green-500' : pct >= 70 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function ProposalCard({
  proposal,
  datasets,
  expanded,
  onToggleExpand,
  onConfirm,
  onReject,
}: {
  proposal: Proposal
  datasets: { id: string; name: string }[]
  expanded: boolean
  onToggleExpand: () => void
  onConfirm: (id: string, adjustments?: ProposalAdjustment[]) => void
  onReject: (id: string) => void
}) {
  const style = PROPOSAL_STATUS_STYLES[proposal.status] || PROPOSAL_STATUS_STYLES.pending
  const StatusIcon = style.icon
  const payload = proposal.proposal_payload
  const sir = payload.parsed_rule || {}
  const resolved = payload.resolved_rule || sir
  const checks = payload.compiled_checks || []
  const subject = (resolved as Record<string, unknown>).subject as Record<string, unknown> | undefined
  const objectEntity = (resolved as Record<string, unknown>).object as Record<string, unknown> | undefined

  // Derive initial editable values from payload
  const firstCheck = checks[0] as Record<string, unknown> | undefined
  const initDatasetId = (firstCheck?.dataset_id as string) ||
    (subject?.dataset_id as string) ||
    (subject?.resolved_dataset as string) || ''
  const initSubjectCol = (subject?.resolved_column as string) || (subject?.raw_text as string) || ''
  const initObjectCol = (objectEntity?.resolved_column as string) || (objectEntity?.raw_text as string) || ''
  const initThresholds = (firstCheck?.thresholds as Record<string, unknown>) || {}
  const initSeverity = (firstCheck?.severity as string) || 'medium'

  // Edit state
  const [editing, setEditing] = useState(false)
  const [editDataset, setEditDataset] = useState(initDatasetId)
  const [editSubjectCol, setEditSubjectCol] = useState(initSubjectCol)
  const [editObjectCol, setEditObjectCol] = useState(initObjectCol)
  const [editThresholdPass, setEditThresholdPass] = useState(
    String((initThresholds as any).threshold_pass ?? 100)
  )
  const [editThresholdWarn, setEditThresholdWarn] = useState(
    String((initThresholds as any).threshold_warn ?? 95)
  )
  const [editSeverity, setEditSeverity] = useState(initSeverity)
  const [editRuleName, setEditRuleName] = useState(proposal.original_prompt)

  const handleConfirm = () => {
    const adjustments: ProposalAdjustment[] = []
    if (editing) {
      if (editDataset !== initDatasetId)
        adjustments.push({ field: 'dataset_id', old_value: initDatasetId, new_value: editDataset })
      if (editSubjectCol !== initSubjectCol)
        adjustments.push({ field: 'subject_column', old_value: initSubjectCol, new_value: editSubjectCol })
      if (editObjectCol !== initObjectCol)
        adjustments.push({ field: 'object_column', old_value: initObjectCol, new_value: editObjectCol })
      if (editSeverity !== initSeverity)
        adjustments.push({ field: 'severity', old_value: initSeverity, new_value: editSeverity })
      if (editThresholdPass !== String((initThresholds as any).threshold_pass ?? 100))
        adjustments.push({ field: 'threshold_pass', old_value: initThresholds, new_value: Number(editThresholdPass) })
      if (editThresholdWarn !== String((initThresholds as any).threshold_warn ?? 95))
        adjustments.push({ field: 'threshold_warn', old_value: initThresholds, new_value: Number(editThresholdWarn) })
      if (editRuleName !== proposal.original_prompt)
        adjustments.push({ field: 'rule_name', old_value: proposal.original_prompt, new_value: editRuleName })
    }
    onConfirm(proposal.proposal_id, adjustments.length > 0 ? adjustments : undefined)
  }

  return (
    <div
      data-testid={`proposal-card-${proposal.proposal_id}`}
      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden"
    >
      {/* Header */}
      <div className="p-5 flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center space-x-3 mb-2">
            <span className={`inline-flex items-center space-x-1 px-2 py-1 text-xs font-medium rounded ${style.bg} ${style.color}`}>
              <StatusIcon className="w-3 h-3" />
              <span className="capitalize">{style.label}</span>
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {new Date(proposal.created_at).toLocaleString()}
            </span>
            {proposal.created_by && (
              <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                <User className="w-3 h-3" />
                {proposal.created_by.slice(0, 8)}…
              </span>
            )}
          </div>
          <p className="text-gray-900 dark:text-gray-200 font-medium">{proposal.original_prompt}</p>
        </div>
        <button
          onClick={onToggleExpand}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded text-gray-400"
        >
          {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      {/* Confidence bars */}
      <div className="px-5 pb-4 grid grid-cols-3 gap-4">
        <ConfidenceBar value={proposal.confidence} label="Overall" />
        <ConfidenceBar value={payload.parse_confidence} label="Parse" />
        <ConfidenceBar value={payload.resolution_confidence} label="Resolution" />
      </div>

      {/* Summary: Rule type, Operator, Entities — always visible */}
      <div className="px-5 pb-4 space-y-3">
        {sir.rule_type ? (
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-20">Rule Type</span>
            <span className="px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 rounded text-xs font-medium">
              {String(sir.rule_type).replace(/_/g, ' ')}
            </span>
          </div>
        ) : null}
        {sir.operator ? (
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-20">Operator</span>
            <span className="text-sm text-gray-700 dark:text-gray-300 font-mono">{String(sir.operator)}</span>
          </div>
        ) : null}
        {subject && (
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-20">Entities</span>
            <div className="flex flex-wrap gap-2">
              <SIREntityChip entity={subject} role="subject" />
              {objectEntity && <SIREntityChip entity={objectEntity} role="object" />}
            </div>
          </div>
        )}
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 p-5 space-y-5">

          {/* ── Edit / View toggle ── */}
          {proposal.status === 'pending' && (
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Rule Configuration</h4>
              <button
                onClick={() => setEditing(!editing)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  editing
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300'
                }`}
              >
                {editing ? <Save className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
                {editing ? 'Editing' : 'Edit'}
              </button>
            </div>
          )}

          {/* ── Editable fields ── */}
          <div className="space-y-3 bg-gray-50 dark:bg-gray-900 rounded-lg p-4 border border-gray-100 dark:border-gray-700">

            {/* Rule name */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Rule Name</label>
              {editing ? (
                <input
                  type="text"
                  value={editRuleName}
                  onChange={(e) => setEditRuleName(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              ) : (
                <p className="text-sm text-gray-700 dark:text-gray-300">{editRuleName}</p>
              )}
            </div>

            {/* Dataset */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase flex items-center gap-1">
                <Database className="w-3 h-3" /> Dataset
              </label>
              {editing ? (
                <select
                  value={editDataset}
                  onChange={(e) => setEditDataset(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">— Select dataset —</option>
                  {datasets.map((ds) => (
                    <option key={ds.id} value={ds.id}>{ds.name}</option>
                  ))}
                </select>
              ) : (
                <p className="text-sm font-mono text-gray-700 dark:text-gray-300">
                  {editDataset
                    ? (datasets.find((d) => d.id === editDataset)?.name || editDataset)
                    : <span className="text-gray-400 italic">not set</span>}
                </p>
              )}
            </div>

            {/* Subject column */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase flex items-center gap-1">
                <Columns className="w-3 h-3" /> Subject Column
              </label>
              {editing ? (
                <input
                  type="text"
                  value={editSubjectCol}
                  onChange={(e) => setEditSubjectCol(e.target.value)}
                  placeholder="e.g. email"
                  className="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              ) : (
                <p className="text-sm font-mono text-gray-700 dark:text-gray-300">
                  {editSubjectCol
                    ? (() => {
                        const dsName = editDataset
                          ? (datasets.find((d) => d.id === editDataset)?.name || '').split('.').pop()
                          : ''
                        return dsName ? `${dsName}.${editSubjectCol}` : editSubjectCol
                      })()
                    : <span className="text-gray-400 italic">not resolved</span>}
                </p>
              )}
            </div>

            {/* Object column (only if present) */}
            {(editObjectCol || editing) && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase flex items-center gap-1">
                  <Columns className="w-3 h-3" /> Object Column
                </label>
                {editing ? (
                  <input
                    type="text"
                    value={editObjectCol}
                    onChange={(e) => setEditObjectCol(e.target.value)}
                    placeholder="e.g. order_date"
                    className="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  />
                ) : (
                  <p className="text-sm font-mono text-gray-700 dark:text-gray-300">
                    {editObjectCol
                      ? (() => {
                          const dsName = editDataset
                            ? (datasets.find((d) => d.id === editDataset)?.name || '').split('.').pop()
                            : ''
                          return dsName ? `${dsName}.${editObjectCol}` : editObjectCol
                        })()
                      : <span className="text-gray-400 italic">not resolved</span>}
                  </p>
                )}
              </div>
            )}

            {/* Severity + Thresholds in a row */}
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Severity</label>
                {editing ? (
                  <select
                    value={editSeverity}
                    onChange={(e) => setEditSeverity(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                    <option value="info">Info</option>
                  </select>
                ) : (
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    editSeverity === 'critical' ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' :
                    editSeverity === 'high' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' :
                    editSeverity === 'medium' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' :
                    'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
                  }`}>
                    {editSeverity}
                  </span>
                )}
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Pass %</label>
                {editing ? (
                  <input type="number" min={0} max={100} value={editThresholdPass}
                    onChange={(e) => setEditThresholdPass(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  />
                ) : (
                  <p className="text-sm font-semibold text-green-700 dark:text-green-400">{editThresholdPass}%</p>
                )}
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Warn %</label>
                {editing ? (
                  <input type="number" min={0} max={100} value={editThresholdWarn}
                    onChange={(e) => setEditThresholdWarn(e.target.value)}
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  />
                ) : (
                  <p className="text-sm font-semibold text-yellow-700 dark:text-yellow-400">{editThresholdWarn}%</p>
                )}
              </div>
            </div>
          </div>

          {/* Check configurations — raw display */}
          {checks.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center space-x-2">
                <Settings className="w-4 h-4 text-gray-500" />
                <span>Check Configuration</span>
              </h4>
              {checks.map((cc: Record<string, unknown>, idx: number) => (
                <ProposalCheckConfigCard key={idx} config={cc} />
              ))}
            </div>
          )}

          {/* Detected columns from SIR */}
          {subject && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center space-x-2">
                <Columns className="w-4 h-4 text-gray-500" />
                <span>Detected Columns</span>
              </h4>
              <div className="flex flex-wrap gap-2">
                <SIREntityChip entity={subject} role="subject" />
                {objectEntity && <SIREntityChip entity={objectEntity} role="object" />}
              </div>
            </div>
          )}

          {/* Glossary matches */}
          {payload.glossary_matches.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center space-x-2">
                <BookOpen className="w-4 h-4 text-blue-500" />
                <span>Glossary Matches</span>
              </h4>
              <div className="space-y-1">
                {payload.glossary_matches.map((m: Record<string, unknown>, i: number) => (
                  <div key={i} className="flex items-center justify-between bg-gray-50 dark:bg-gray-900 rounded px-3 py-2 text-sm">
                    <div>
                      <span className="text-gray-800 dark:text-gray-200 font-medium">{String(m.business_name)}</span>
                      {m.domain ? <span className="ml-2 text-xs text-purple-600 dark:text-purple-400">({String(m.domain)})</span> : null}
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded">{String(m.match_type)}</span>
                      <span className="text-xs text-gray-500">{Math.round(Number(m.match_score || 0) * 100)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Parsed rule (SIR) */}
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-blue-500" />
              <span>Parsed Rule (SIR)</span>
            </h4>
            <details className="text-xs">
              <summary className="text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-300">View raw SIR</summary>
              <pre className="mt-2 bg-gray-50 dark:bg-gray-900 rounded p-3 text-xs text-gray-600 dark:text-gray-400 overflow-x-auto max-h-48">
                {JSON.stringify(payload.parsed_rule, null, 2)}
              </pre>
            </details>
          </div>

          {/* Resolution evidence */}
          {Object.keys(payload.resolution_evidence).length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center space-x-2">
                <Database className="w-4 h-4 text-green-500" />
                <span>Resolution Evidence</span>
              </h4>
              <details className="text-xs">
                <summary className="text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-300">View resolution details</summary>
                <pre className="mt-2 bg-gray-50 dark:bg-gray-900 rounded p-3 text-xs text-gray-600 dark:text-gray-400 overflow-x-auto max-h-32">
                  {JSON.stringify(payload.resolution_evidence, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {proposal.status === 'pending' && (
        <div className="border-t border-gray-200 dark:border-gray-700 px-5 py-3 flex items-center justify-between">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            {editing ? 'Review adjustments above, then confirm' : 'Expand to review & edit before confirming'}
          </p>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => onReject(proposal.proposal_id)}
              className="px-4 py-2 bg-red-50 hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400 rounded-lg text-sm flex items-center space-x-2"
            >
              <XCircle className="w-4 h-4" />
              <span>Reject</span>
            </button>
            <button
              onClick={handleConfirm}
              data-testid={`proposal-confirm-btn-${proposal.proposal_id}`}
              className="px-4 py-2 bg-green-50 hover:bg-green-100 dark:bg-green-900/20 dark:hover:bg-green-900/30 text-green-600 dark:text-green-400 rounded-lg text-sm flex items-center space-x-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{editing ? 'Confirm with Adjustments' : 'Confirm'}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── SIR Entity Chip ──────────────────────────────────────────────────────────

function SIREntityChip({ entity, role }: { entity: Record<string, unknown>; role: string }) {
  const col = String(entity.resolved_column || entity.raw_text || 'unknown')
  const dataset = entity.resolved_dataset ? String(entity.resolved_dataset) : null
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded text-xs">
      {dataset && <span className="text-blue-400 font-mono">{dataset}.</span>}
      <span className="font-medium">{col}</span>
      <span className="text-blue-500 dark:text-blue-400">({role})</span>
    </span>
  )
}

// ── Proposal Check Config Card ───────────────────────────────────────────────

function ProposalCheckConfigCard({ config }: { config: Record<string, unknown> }) {
  const dimension = String(config.check_dimension || 'unknown').toUpperCase()
  const subtype = String(config.check_subtype || '')
  const severity = String(config.severity || 'medium')
  const ruleName = String(config.rule_name || '')
  const columns = Array.isArray(config.columns) ? config.columns.map(String) : []
  const thresholds = (config.thresholds || {}) as Record<string, unknown>
  const nodeConfig = (config.config || {}) as Record<string, unknown>

  const severityColor =
    severity === 'critical' ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' :
    severity === 'high' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' :
    severity === 'medium' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' :
    'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'

  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 space-y-2 border border-gray-100 dark:border-gray-700">
      {/* Dimension + Subtype + Severity */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 rounded text-xs font-semibold uppercase">
          {dimension}
        </span>
        <span className="px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded text-xs font-medium">
          {subtype}
        </span>
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${severityColor}`}>
          {severity}
        </span>
      </div>

      {/* Rule name */}
      {ruleName && (
        <div>
          <span className="text-xs text-gray-500 dark:text-gray-400">Rule: </span>
          <span className="text-xs font-mono text-gray-700 dark:text-gray-300">{ruleName}</span>
        </div>
      )}

      {/* Columns */}
      {columns.length > 0 && (
        <div>
          <span className="text-xs text-gray-500 dark:text-gray-400">Columns: </span>
          <span className="text-xs font-mono text-gray-700 dark:text-gray-300">{columns.join(', ')}</span>
        </div>
      )}

      {/* Thresholds */}
      {Object.keys(thresholds).length > 0 && (
        <div className="flex gap-4 text-xs">
          {thresholds.threshold_pass != null && (
            <div>
              <span className="text-gray-500 dark:text-gray-400">Pass: </span>
              <span className="font-semibold text-green-700 dark:text-green-400">{String(thresholds.threshold_pass)}%</span>
            </div>
          )}
          {thresholds.threshold_warn != null && (
            <div>
              <span className="text-gray-500 dark:text-gray-400">Warn: </span>
              <span className="font-semibold text-yellow-700 dark:text-yellow-400">{String(thresholds.threshold_warn)}%</span>
            </div>
          )}
          {thresholds.null_handling != null && (
            <div>
              <span className="text-gray-500 dark:text-gray-400">Nulls: </span>
              <span className="font-medium text-gray-700 dark:text-gray-300">{String(thresholds.null_handling)}</span>
            </div>
          )}
        </div>
      )}

      {/* Node config details */}
      {Object.keys(nodeConfig).length > 0 && (
        <details className="text-xs">
          <summary className="text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-300">Node config details</summary>
          <div className="mt-1 bg-white dark:bg-gray-800 rounded p-2 font-mono text-gray-600 dark:text-gray-400 overflow-x-auto">
            {Object.entries(nodeConfig)
              .filter(([k]) => k !== 'columns')
              .map(([k, v]) => (
                <div key={k}>
                  <span className="text-gray-400">{k}: </span>
                  <span>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                </div>
              ))}
          </div>
        </details>
      )}
    </div>
  )
}
