/**
 * useFlowBuilder Hook - Manages all state and logic for the flow builder
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams, useNavigate, useParams } from 'react-router-dom'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import flowService, { FlowDefinition, FlowNode as APIFlowNode, FlowConnection, NodeType, FlowStatus, ExecutionStatus } from '../../services/flow'
import { listDataSources } from '../../services/datasource'
import { getRule } from '../../services/ruleService'
import { listDatasets, getDataset } from '../../services/datasetService'
import { FlowNode, DQCheck, PromptMessage } from './types'

export function useFlowBuilder() {
  const { currentWorkspace } = useWorkspace()
  const { workspace_id: urlWorkspaceId } = useParams<{ workspace_id?: string }>()
  // Prefer URL param so workspace-scoped routes (/hub/ws/:workspace_id/...) work
  // even if the global WorkspaceContext is pointing at a different workspace.
  const activeWorkspaceId = urlWorkspaceId || currentWorkspace?.workspace_id
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  
  // Flow metadata
  const [flowId, setFlowId] = useState<string | null>(null)
  const [flowName, setFlowName] = useState<string>('Untitled Flow')
  const [flowDescription, setFlowDescription] = useState<string>('')
  const [flowNodes, setFlowNodes] = useState<FlowNode[]>([])
  
  // UI State
  const [selectedNode, setSelectedNode] = useState<FlowNode | null>(null)
  const [activeTab, setActiveTab] = useState<'flow' | 'datasources' | 'runs' | 'reports'>('flow')
  const [selectedExecutionForReport, setSelectedExecutionForReport] = useState<any | null>(null)
  const [showLibrary, setShowLibrary] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  
  // Canvas interaction
  const [draggedNode, setDraggedNode] = useState<FlowNode | null>(null)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [connectionStart, setConnectionStart] = useState<FlowNode | null>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  
  // Data sources (still loaded for AI prompt and legacy compatibility)
  const [searchTerm, setSearchTerm] = useState('')
  const [realDataSources, setRealDataSources] = useState<any[]>([])
  
  // Check configuration
  const [showCheckConfig, setShowCheckConfig] = useState(false)
  const [showSourceConfig, setShowSourceConfig] = useState(false)
  const [checkConfig, setCheckConfig] = useState<any>({
    ruleName: '',
    targetTable: '',
    severityLevel: 'error',
    columns: [],
    checkNulls: true,
    checkEmpty: true,
    threshold: 100
  })
  
  // AI Prompting
  const [isProcessingPrompt, setIsProcessingPrompt] = useState(false)
  const [promptMessage, setPromptMessage] = useState<PromptMessage | null>(null)
  const [pendingTasks, setPendingTasks] = useState<any>(null) // Store pending tasks after data source selection
  
  // Loading and messages
  const [isSaving, setIsSaving] = useState(false)
  const [isExecuting, setIsExecuting] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string>('')
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved')
  
  // Auto-save timer
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastSaveDataRef = useRef<string>('')
  const saveFlowAsyncRef = useRef<(() => Promise<void>) | null>(null)
  const isSavingRef = useRef(false)
  
  // Executions and reports (for other tabs)
  const [flowExecutions, setFlowExecutions] = useState<any[]>([])
  const [selectedExecution, setSelectedExecution] = useState<any | null>(null)
  const [currentExecution, setCurrentExecution] = useState<any | null>(null)
  const executionPollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  
  // Load real data sources
  useEffect(() => {
    const loadDataSources = async () => {
      if (!activeWorkspaceId) return
      try {
        // Fetch both database sources AND file assets
        const [sourcesResp, dataAssets] = await Promise.all([
          listDataSources(activeWorkspaceId, { page_size: 100 }),
          // NOTE: data assets endpoint (ingestion) is separate from F004 data sources
          fetch(`/api/v1/ingestion/workspaces/${activeWorkspaceId}/data-assets`)
            .then(res => res.ok ? res.json() : [])
            .catch(() => [])
        ])
        
        // Build a unified list for the flow builder canvas
        const expandedSources: any[] = []

        // Process F004 data sources — map to canvas-friendly shape
        for (const source of (sourcesResp.items ?? [])) {
          expandedSources.push({
            ...source,
            // Normalised aliases expected by the canvas / RuleFlowBuilder
            id: source.data_source_id,
            source_id: source.data_source_id,
            name: source.source_name,
            display_name: source.source_name,
            type: source.source_type,
          })
        }
        
        // Process file assets (CSV, Excel, Parquet, JSON)
        if (Array.isArray(dataAssets)) {
          dataAssets.forEach((asset: any) => {
            // Only include file-type assets, not database tables (already included above)
            if (asset.type !== 'table' && asset.type !== 'database') {
              expandedSources.push({
                id: asset.id,
                file_id: asset.id,
                name: asset.name,
                display_name: asset.name,
                type: asset.type,
                source_type: 'file',
                file_type: asset.type,
                file_path: asset.metadata?.file_path,
                metadata: {
                  columns: asset.metadata?.columns || [],
                  rowCount: asset.metadata?.rows,
                  fileSize: asset.metadata?.file_size
                }
              })
            }
          })
        }
        
        setRealDataSources(expandedSources)
      } catch (error: any) {
        console.error('Error loading data sources:', error)
      }
    }
    loadDataSources()
  }, [activeWorkspaceId])

  // Hydrate source-node configs with column metadata once data sources are
  // available. Source nodes saved by the auto-flow generator only carry
  // {data_source_id, table_name, schema_name}, so without this pass the
  // CheckConfigPanel would display "Connected source has no column metadata."
  const hydratedSourcesRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (flowNodes.length === 0) return
    const pendingSources = flowNodes.filter((n) => {
      if (n.type !== 'source') return false
      if (hydratedSourcesRef.current.has(n.id)) return false
      const cfg = (n.config || {}) as Record<string, any>
      const hasColumns = Array.isArray(cfg.metadata?.columns) && cfg.metadata.columns.length > 0
      const hasDatasetId = Boolean(cfg.dataset_id)
      // Need hydration if either columns or dataset_id is missing
      return !hasColumns || !hasDatasetId
    })
    if (pendingSources.length === 0) return

    let cancelled = false
    ;(async () => {
      // Build a workspace-wide dataset lookup once: key → DatasetListItem
      const datasetIndex: Record<string, any> = {}
      try {
        if (activeWorkspaceId) {
          const datasets = await listDatasets(activeWorkspaceId, { page_size: 100, status: 'active' as any })
          const items: any[] = (datasets as any)?.items || (Array.isArray(datasets) ? datasets : [])
          for (const ds of items) {
            const key = `${ds.schema_name || ''}::${ds.physical_identifier || ds.dataset_name || ''}`
            datasetIndex[key] = ds
            // Also index by data_source_id+table_name as a fallback
            if (ds.data_source_id) {
              datasetIndex[`${ds.data_source_id}::${ds.physical_identifier || ds.dataset_name || ''}`] = ds
            }
          }
        }
      } catch (err) {
        console.warn('[hydrateSources] Failed to list datasets', err)
      }

      // Each update carries shaped column objects + dataset descriptor
      type SourceUpdate = {
        columns: Array<{ column_name: string; data_type?: string; nullable?: boolean }>
        dataset?: {
          dataset_id: string
          dataset_name?: string
          physical_identifier?: string
          data_source_id?: string
          data_source_name?: string
          dataset_type?: string
          field_count?: number
          schema_name?: string
        }
      }
      const updates: Record<string, SourceUpdate> = {}
      await Promise.all(
        pendingSources.map(async (n) => {
          const cfg = (n.config || {}) as Record<string, any>
          const tableName = cfg.table_name
          const schemaName = cfg.schema_name
          const dataSourceId = cfg.data_source_id

          // Try to resolve a dataset record from the registry first so the
          // DatasetConfigPanel sees a configured node (it requires dataset_id).
          let datasetItem: any | undefined
          if (tableName) {
            datasetItem =
              datasetIndex[`${schemaName || ''}::${tableName}`] ||
              (dataSourceId ? datasetIndex[`${dataSourceId}::${tableName}`] : undefined)
          }

          // 1) Data source listing entry may already carry metadata.columns
          const ds = realDataSources.find((d: any) =>
            (dataSourceId && (d.id === dataSourceId || d.data_source_id === dataSourceId || d.source_id === dataSourceId))
            || (tableName && d.table_name === tableName && (!schemaName || d.schema_name === schemaName)),
          )
          if (ds && Array.isArray(ds.metadata?.columns) && ds.metadata.columns.length > 0) {
            const cols = ds.metadata.columns.map((c: any) =>
              typeof c === 'string'
                ? { column_name: c }
                : { column_name: c.column_name || c.name, data_type: c.data_type, nullable: c.nullable },
            ).filter((c: any) => c.column_name)
            updates[n.id] = {
              columns: cols,
              dataset: datasetItem
                ? {
                    dataset_id: datasetItem.dataset_id,
                    dataset_name: datasetItem.dataset_name,
                    physical_identifier: datasetItem.physical_identifier,
                    data_source_id: datasetItem.data_source_id,
                    data_source_name: datasetItem.data_source_name,
                    dataset_type: datasetItem.dataset_type,
                    field_count: datasetItem.field_count,
                    schema_name: datasetItem.schema_name,
                  }
                : undefined,
            }
            return
          }

          // 2) Fall back to dataset registry detail
          if (!datasetItem || !activeWorkspaceId) return
          try {
            const detail: any = await getDataset(activeWorkspaceId, datasetItem.dataset_id)
            const fields: any[] = detail?.fields || []
            const cols = fields
              .map((f: any) => ({ column_name: f.field_name, data_type: f.data_type, nullable: f.nullable }))
              .filter((c: any) => c.column_name)
            updates[n.id] = {
              columns: cols,
              dataset: {
                dataset_id: detail.dataset_id || datasetItem.dataset_id,
                dataset_name: detail.dataset_name || datasetItem.dataset_name,
                physical_identifier: detail.physical_identifier || datasetItem.physical_identifier,
                data_source_id: detail.data_source_id || datasetItem.data_source_id,
                data_source_name: detail.data_source_name || datasetItem.data_source_name,
                dataset_type: detail.dataset_type || datasetItem.dataset_type,
                field_count: detail.field_count ?? datasetItem.field_count,
                schema_name: detail.schema_name || datasetItem.schema_name,
              },
            }
          } catch (err) {
            console.warn(`[hydrateSources] Failed to fetch dataset ${datasetItem.dataset_id}`, err)
          }
        }),
      )

      if (cancelled || Object.keys(updates).length === 0) return
      setFlowNodes((prev) =>
        prev.map((n) => {
          const upd = updates[n.id]
          if (!upd) return n
          hydratedSourcesRef.current.add(n.id)
          const cfg = (n.config || {}) as Record<string, any>
          const colNames = upd.columns.map((c) => c.column_name)
          return {
            ...n,
            config: {
              ...cfg,
              ...(upd.dataset || {}),
              // Keep table_name aligned with physical_identifier when resolved
              table_name: upd.dataset?.physical_identifier || cfg.table_name,
              schema_name: upd.dataset?.schema_name || cfg.schema_name,
              metadata: { ...(cfg.metadata || {}), columns: upd.columns },
              columns: colNames,
            },
          }
        }),
      )
      // Mark even those we couldn't resolve so we don't loop
      pendingSources.forEach((n) => {
        if (!updates[n.id]) hydratedSourcesRef.current.add(n.id)
      })
    })()

    return () => {
      cancelled = true
    }
  }, [activeWorkspaceId, realDataSources, flowNodes])

  const loadFlow = useCallback(async (id: string) => {
    if (!activeWorkspaceId) return
    try {
      const flow = await flowService.getFlow(activeWorkspaceId, id)
      
      setFlowId(flow.id)
      setFlowName(flow.name)
      setFlowDescription(flow.description || '')
      
      // Convert API nodes to local format
      const localNodes: FlowNode[] = flow.flow_definition.nodes.map((apiNode) => ({
        id: apiNode.id,
        type: apiNode.type === NodeType.SOURCE ? 'source' : 'check',
        name: apiNode.label,
        checkType: apiNode.checkType,
        x: apiNode.position.x,
        y: apiNode.position.y,
        config: apiNode.config,
        connections: [],
      }))

      // Reconstruct connections
      flow.flow_definition.connections.forEach((conn: any) => {
        // Handle both formats: {from, to} and {source, target}
        const fromId = conn.from || conn.source
        const toId = conn.to || conn.target
        
        const sourceNode = localNodes.find(n => n.id === fromId)
        if (sourceNode && !sourceNode.connections.includes(toId)) {
          sourceNode.connections.push(toId)
        }
      })

      // Hydrate check nodes whose config carries only a rule_id by fetching
      // the underlying rule and merging its parameters / target columns /
      // thresholds into the node config so the editor shows the real values.
      // Mirror of backend CONFORMITY_STANDARDS — used to derive the regex
      // `pattern` when only `standard_name` (e.g. 'email') is stored.
      const CONFORMITY_PATTERNS: Record<string, string> = {
        email: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$',
        email_rfc5322: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$',
        phone: '^\\+?[\\d\\s\\-\\.\\(\\)]{7,}$',
        e164: '^\\+[1-9]\\d{1,14}$',
        iso_8601: '^\\d{4}-\\d{2}-\\d{2}(T\\d{2}:\\d{2}(:\\d{2})?(\\.\\d+)?(Z|[+-]\\d{2}:\\d{2})?)?$',
        date_iso: '^\\d{4}-\\d{2}-\\d{2}(T\\d{2}:\\d{2}(:\\d{2})?(\\.\\d+)?(Z|[+-]\\d{2}:\\d{2})?)?$',
        iso_3166: '^[A-Z]{2}$',
        iso_4217: '^[A-Z]{3}$',
        iban: '^[A-Z]{2}\\d{2}[A-Z0-9]{4,30}$',
        url: '^https?://[^\\s/$.?#].[^\\s]*$',
        uuid: '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
        ip_address: '^((25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\.){3}(25[0-5]|2[0-4]\\d|[01]?\\d\\d?)$',
        credit_card: '^\\d{13,19}$',
        postal_code: '^[A-Z0-9]{3,10}(-[A-Z0-9]{3,10})?$',
        ssn: '^\\d{3}-\\d{2}-\\d{4}$',
      }
      const derivePattern = (cfg: Record<string, any>): string => {
        if (cfg.pattern) return cfg.pattern as string
        if (cfg.regex_pattern) return cfg.regex_pattern as string
        const std = (cfg.standard_name as string) || ''
        return std ? (CONFORMITY_PATTERNS[std] || '') : ''
      }
      // Mirror of backend `_OP_ALIASES` for cross_field comparison operator.
      // Maps any backend-accepted alias (or date_operator value) to the
      // canonical UI dropdown values declared in validity.ts.
      const COMPARISON_OPERATOR_ALIASES: Record<string, string> = {
        '=': 'equals', '==': 'equals', eq: 'equals', equal: 'equals', equals: 'equals',
        '!=': 'not_equals', '<>': 'not_equals', ne: 'not_equals',
        not_equal: 'not_equals', not_equals: 'not_equals',
        '<': 'less_than', lt: 'less_than', less: 'less_than',
        less_than: 'less_than', before: 'less_than',
        '<=': 'less_equal', lte: 'less_equal', less_equal: 'less_equal',
        less_than_or_equal: 'less_equal', on_or_before: 'less_equal', not_after: 'less_equal',
        '>': 'greater_than', gt: 'greater_than', greater: 'greater_than',
        greater_than: 'greater_than', after: 'greater_than',
        '>=': 'greater_equal', gte: 'greater_equal', greater_equal: 'greater_equal',
        greater_than_or_equal: 'greater_equal', on_or_after: 'greater_equal', not_before: 'greater_equal',
      }
      const deriveComparisonOperator = (cfg: Record<string, any>): string => {
        const raw = cfg.comparison_operator || cfg.date_operator
        if (!raw) return ''
        return COMPARISON_OPERATOR_ALIASES[String(raw).trim().toLowerCase()] || String(raw)
      }
      await Promise.all(
        localNodes.map(async (n) => {
          if (n.type !== 'check') return
          const cfg = (n.config || {}) as Record<string, any>
          const ruleId = cfg.rule_id
          // Already hydrated path: only ensure regex `pattern` is filled in
          // (e.g. flow saved with subtype=regex + standard_name='email' but
          // no explicit pattern — derive it from CONFORMITY_PATTERNS).
          if (ruleId && (cfg.subtype || (Array.isArray(cfg.columns) && cfg.columns.length > 0))) {
            const patches: Record<string, unknown> = {}
            if (cfg.subtype === 'regex' && !cfg.pattern) {
              const p = derivePattern(cfg)
              if (p) patches.pattern = p
            }
            if (cfg.subtype === 'cross_field' && !cfg.comparison_operator) {
              const op = deriveComparisonOperator(cfg)
              if (op) patches.comparison_operator = op
            }
            if (Object.keys(patches).length > 0) n.config = { ...cfg, ...patches }
            return
          }
          if (!ruleId) return
          try {
            const rule = await getRule(activeWorkspaceId, ruleId)
            const canonical = (rule.canonical_rule || {}) as Record<string, any>
            const params = (canonical.parameters || {}) as Record<string, any>
            const subtype = (params.check_subtype as string)
              || (params.validation_type as string)
              || rule.rule_type
              || n.checkType
            const standardName = (params.standard_name as string) || ''
            const derivedPattern = !params.pattern && !params.regex_pattern && standardName
              ? CONFORMITY_PATTERNS[standardName] || ''
              : ''
            // Cross-field rules may store the operator under `date_operator`
            // or use any of the backend aliases (e.g. 'on_or_after').
            // Normalize it for the cross_field UI dropdown.
            const derivedComparisonOperator = subtype === 'cross_field' && !params.comparison_operator
              ? deriveComparisonOperator(params)
              : ''
            n.config = {
              ...cfg,
              ...params,
              subtype,
              ...(derivedPattern ? { pattern: derivedPattern } : {}),
              ...((!params.pattern && params.regex_pattern) ? { pattern: params.regex_pattern } : {}),
              ...(derivedComparisonOperator ? { comparison_operator: derivedComparisonOperator } : {}),
              columns: (rule.target_columns && rule.target_columns.length > 0)
                ? rule.target_columns
                : (Array.isArray(cfg.columns) ? cfg.columns : []),
              ruleName: rule.name || cfg.ruleName || '',
              description: rule.description || cfg.description || '',
              severity: (params.severity as string) || (canonical.severity as string) || 'medium',
              threshold_pass: params.threshold_pass ?? cfg.threshold_pass ?? 100,
              threshold_warn: params.threshold_warn ?? cfg.threshold_warn ?? null,
              null_handling: (params.null_handling as string) || cfg.null_handling || 'fail',
              filter_expression: (params.filter_expression as string) || cfg.filter_expression || '',
              data_source_id: rule.data_source_id || cfg.data_source_id,
              target_schema: rule.target_schema || cfg.target_schema,
              target_table: rule.target_table || cfg.target_table,
            }
            // Refine local checkType (dimension) if available
            if (canonical.dimension) {
              n.checkType = canonical.dimension as string
            }
          } catch (err) {
            console.warn(`[loadFlow] Failed to hydrate check node ${n.id} (rule ${ruleId})`, err)
          }
        })
      )

      setFlowNodes(localNodes)
      
      // Load executions for this flow
      try {
        const executions = await flowService.getFlowExecutions(activeWorkspaceId, id)
        setFlowExecutions(Array.isArray(executions) ? executions : [])
      } catch (error) {
        console.error('Error loading executions:', error)
        setFlowExecutions([])
      }
      
      // Initialize lastSaveDataRef to prevent auto-save trigger on load
      setTimeout(() => {
        const initialData = JSON.stringify({
          name: flow.name,
          description: flow.description || '',
          nodes: localNodes.map(n => ({
            id: n.id,
            type: n.type,
            name: n.name,
            checkType: n.checkType,
            x: n.x,
            y: n.y,
            config: n.config,
            connections: n.connections
          }))
        })
        lastSaveDataRef.current = initialData
      }, 100)
    } catch (error: any) {
      console.error('❌ Error loading flow:', error)
    }
  }, [activeWorkspaceId])
  
  // Load flow from URL parameter
  useEffect(() => {
    const flowIdParam = searchParams.get('id')
    const tabParam = searchParams.get('tab') as 'datasources' | 'runs' | 'reports' | null
    
    // Set active tab from URL if present
    if (tabParam && ['datasources', 'runs', 'reports'].includes(tabParam)) {
      setActiveTab(tabParam)
    }
    
    if (flowIdParam && activeWorkspaceId) {
      loadFlow(flowIdParam)
    } else if (!flowIdParam) {
      // Clear flow state when there's no ID
      setFlowId(null)
      setFlowNodes([])
      setFlowName('Untitled Flow')
      setFlowDescription('')
    }
  }, [searchParams, activeWorkspaceId, loadFlow])

  const handleAddComponent = (component: DQCheck) => {
    const newNode: FlowNode = {
      id: `node_${Date.now()}`,
      type: component.id === 'dataset' ? 'source' : 'check',
      checkType: component.type,
      name: component.name,
      x: 150 + flowNodes.length * 50,
      y: 150 + flowNodes.length * 30,
      config: {},
      connections: []
    }
    
    setFlowNodes(prev => [...prev, newNode])
  }

  // Auto-save function with debouncing (Dataiku-style)
  const saveFlowAsync = useCallback(async () => {
    if (!activeWorkspaceId) {
      console.warn('Cannot save: No workspace selected')
      return
    }

    // Prevent concurrent saves (race condition guard for new flows)
    if (isSavingRef.current) return
    isSavingRef.current = true

    setIsSaving(true)
    setSaveStatus('saving')
    
    try {
      const apiNodes: APIFlowNode[] = flowNodes.map((node) => ({
        id: node.id,
        type: node.type === 'source' ? NodeType.SOURCE : NodeType.CHECK,
        label: node.name || node.checkType || 'Node',
        checkType: node.checkType,
        position: { x: node.x, y: node.y },
        config: node.config,
      }))

      const apiConnections: FlowConnection[] = []
      flowNodes.forEach((node) => {
        node.connections.forEach((targetId) => {
          apiConnections.push({ id: `${node.id}-${targetId}`, from: node.id, to: targetId })
        })
      })
      
      const flowDefinition: FlowDefinition = {
        nodes: apiNodes,
        connections: apiConnections,
        metadata: { 
          created_with: 'visual_builder', 
          version: '1.0',
          last_modified: new Date().toISOString()
        },
      }

      // Build serialized save data for change detection
      const currentSaveData = JSON.stringify({
        name: flowName,
        description: flowDescription,
        nodes: apiNodes,
        connections: apiConnections
      })

      if (flowId) {
        await flowService.updateFlow(activeWorkspaceId, flowId, {
          name: flowName,
          description: flowDescription,
          flow_definition: flowDefinition,
        })
        
        // Ensure URL has the flow ID (in case it was created but URL wasn't updated)
        const currentFlowIdInUrl = searchParams.get('id')
        if (currentFlowIdInUrl !== flowId) {
          const base = window.location.pathname
          navigate(`${base}?id=${flowId}`, { replace: true })
        }
      } else {
        const newFlow = await flowService.createFlow(activeWorkspaceId, {
          name: flowName,
          description: flowDescription,
          flow_definition: flowDefinition,
          status: FlowStatus.DRAFT,
        })
        setFlowId(newFlow.id)
        // Update URL with new flow ID so refresh works
        const base = window.location.pathname
        navigate(`${base}?id=${newFlow.id}`, { replace: true })
      }

      // Update lastSaveDataRef AFTER successful save (not before)
      lastSaveDataRef.current = currentSaveData
      setSaveStatus('saved')
      setSaveMessage('')
    } catch (error: any) {
      console.error('Error saving flow:', error)
      setSaveStatus('unsaved')
      setSaveMessage(`Error: ${error.message}`)
      setTimeout(() => setSaveMessage(''), 5000)
    } finally {
      setIsSaving(false)
      isSavingRef.current = false
    }
  }, [activeWorkspaceId, flowNodes, flowName, flowDescription, flowId])

  // Keep ref updated with latest save function
  useEffect(() => {
    saveFlowAsyncRef.current = saveFlowAsync
  }, [saveFlowAsync])

  // Trigger auto-save when flow data changes (debounced by 2 seconds)
  useEffect(() => {
    // Don't auto-save a brand-new flow that has no nodes yet (prevents orphan "Untitled Flow")
    if (!flowId && flowNodes.length === 0) {
      setSaveStatus('saved')
      return
    }

    // Check if data has actually changed
    const currentData = JSON.stringify({
      name: flowName,
      description: flowDescription,
      nodes: flowNodes.map(n => ({
        id: n.id,
        type: n.type,
        name: n.name,
        checkType: n.checkType,
        x: n.x,
        y: n.y,
        config: n.config,
        connections: n.connections
      }))
    })

    // Initialize lastSaveDataRef on first run if empty
    if (!lastSaveDataRef.current && flowId) {
      lastSaveDataRef.current = currentData
      setSaveStatus('saved')
      return
    }

    if (currentData === lastSaveDataRef.current) {
      return
    }

    // Mark as unsaved
    setSaveStatus('unsaved')

    // Clear existing timer
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current)
    }

    // Set new timer for auto-save (2 second debounce)
    autoSaveTimerRef.current = setTimeout(() => {
      // Call the latest version of saveFlowAsync via ref
      if (saveFlowAsyncRef.current) {
        saveFlowAsyncRef.current()
      }
    }, 2000)

    // Cleanup on unmount
    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current)
      }
    }
  }, [flowNodes, flowName, flowDescription, flowId]) // Removed saveFlowAsync to prevent recreation loop

  // Manual save function (kept for backwards compatibility if needed)
  const handleSaveFlow = useCallback(async () => {
    // Clear the auto-save timer and save immediately
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current)
    }
    await saveFlowAsync()
  }, [saveFlowAsync])

  const handleExecuteFlow = useCallback(async () => {
    if (!activeWorkspaceId || !flowId) {
      console.error('Cannot execute: missing workspace or flow ID')
      return
    }

    setIsExecuting(true)
    try {
      // Save the flow first to ensure latest changes are persisted
      await saveFlowAsync()

      // Execute the flow
      const execution = await flowService.executeFlow(activeWorkspaceId, flowId)
      
      setCurrentExecution(execution)
      setSaveMessage('✅ Flow execution started')
      
      // Start polling for execution status
      startExecutionPolling(execution.id)
      
      // Optionally navigate to the runs tab to see the execution
      setActiveTab('runs')
      
      // Refresh executions list
      if (flowId) {
        const executions = await flowService.getFlowExecutions(activeWorkspaceId, flowId)
        setFlowExecutions(Array.isArray(executions) ? executions : [])
      }
    } catch (error: any) {
      console.error('Error executing flow:', error)
      
      // Check if it's a validation error with details
      let errorMsg = error.response?.data?.detail || error.message
      
      if (error.response?.data?.error_details?.errors) {
        const validationErrors = error.response.data.error_details.errors
        if (Array.isArray(validationErrors) && validationErrors.length > 0) {
          // Show first validation error
          const firstError = validationErrors[0]
          errorMsg = firstError.message || firstError
        }
      }
      
      setSaveMessage(`❌ ${errorMsg}`)
      setTimeout(() => setSaveMessage(''), 8000)
      setIsExecuting(false)
    }
  }, [activeWorkspaceId, flowId, saveFlowAsync])

  const startExecutionPolling = useCallback((executionId: string) => {
    // Clear any existing polling
    if (executionPollingRef.current) {
      clearInterval(executionPollingRef.current)
    }

    // Poll every 2 seconds
    executionPollingRef.current = setInterval(async () => {
      if (!activeWorkspaceId) return

      try {
        const execution = await flowService.getExecution(activeWorkspaceId, executionId)
        setCurrentExecution(execution)

        // Update message based on status
        if (execution.status === ExecutionStatus.RUNNING) {
          setSaveMessage(`🔄 Running... (${execution.nodes_executed}/${execution.nodes_executed + execution.nodes_failed + execution.nodes_skipped} nodes)`)
        } else if (execution.status === ExecutionStatus.COMPLETED) {
          setSaveMessage(`✅ Completed! ${execution.nodes_passed} passed, ${execution.nodes_failed} failed`)
          setTimeout(() => setSaveMessage(''), 5000)
          stopExecutionPolling()
          setIsExecuting(false)
          
          // Refresh executions list then switch to report
          if (flowId) {
            const executions = await flowService.getFlowExecutions(activeWorkspaceId, flowId)
            setFlowExecutions(Array.isArray(executions) ? executions : [])
          }
          // Auto-navigate to the report for this execution
          setSelectedExecutionForReport(execution)
          setActiveTab('reports')
        } else if (execution.status === ExecutionStatus.FAILED) {
          setSaveMessage(`❌ Failed: ${execution.error_message || 'Unknown error'}`)
          setTimeout(() => setSaveMessage(''), 5000)
          stopExecutionPolling()
          setIsExecuting(false)
          
          // Refresh executions list then switch to report
          if (flowId) {
            const executions = await flowService.getFlowExecutions(activeWorkspaceId, flowId)
            setFlowExecutions(Array.isArray(executions) ? executions : [])
          }
          // Auto-navigate to the report for this execution
          setSelectedExecutionForReport(execution)
          setActiveTab('reports')
        } else if (execution.status === ExecutionStatus.CANCELLED) {
          setSaveMessage('⚠️ Execution cancelled')
          setTimeout(() => setSaveMessage(''), 5000)
          stopExecutionPolling()
          setIsExecuting(false)
        }
      } catch (error: any) {
        console.error('Error polling execution:', error)
        // Don't stop polling on error, just log it
      }
    }, 2000)
  }, [activeWorkspaceId, flowId])

  const stopExecutionPolling = useCallback(() => {
    if (executionPollingRef.current) {
      clearInterval(executionPollingRef.current)
      executionPollingRef.current = null
    }
  }, [])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      stopExecutionPolling()
    }
  }, [])

  const handleAiPromptSubmit = async (prompt: string) => {
    if (!activeWorkspaceId || !prompt.trim()) return

    setIsProcessingPrompt(true)
    setPromptMessage(null)
    setPendingTasks(null) // Clear any pending tasks

    try {
      const currentFlowConfig = {
        nodes: flowNodes.map(node => ({
          id: node.id,
          type: node.type === 'source' ? NodeType.SOURCE : NodeType.CHECK,
          label: node.name || node.checkType || 'Node',
          checkType: node.checkType,
          position: { x: node.x, y: node.y },
          config: node.config
        })),
        connections: flowNodes.flatMap(node => 
          node.connections.map(targetId => ({
            id: `${node.id}-${targetId}`,
            from: node.id,
            to: targetId
          }))
        )
      }

      // Include available data sources for AI to search and suggest
      const result = await flowService.aiBuildFlow(
        activeWorkspaceId, 
        prompt, 
        currentFlowConfig,
        realDataSources
      )

      // Handle suggested data sources
      if (result.suggested_data_sources && result.suggested_data_sources.length > 0) {
        setPendingTasks(result.pending_tasks) // Store pending tasks for later
        setPromptMessage({ 
          type: 'suggestions', 
          text: result.message,
          suggestions: result.suggested_data_sources
        })
        return
      }

      if (result.needs_clarification) {
        setPromptMessage({ type: 'question', text: result.clarification_questions.join('\n') })
      } else if (result.success && result.flow_updates) {
        const updates = result.flow_updates

        // Merge new nodes with existing ones
        setFlowNodes(prev => {
          // Start with all existing nodes
          let updatedNodes = [...prev]
          
          // Get IDs of existing nodes to avoid duplicates
          const existingIds = new Set(prev.map(n => n.id))

          // Add only NEW nodes (those not already in the flow)
          if (updates.nodes && updates.nodes.length > 0) {
            const nodesToAdd = updates.nodes.filter((node: any) => !existingIds.has(node.id))
            
            // Calculate non-overlapping positions for each new node
            const nodeWidth = 220
            const nodeHeight = 120
            const margin = 30
            
            nodesToAdd.forEach((node: any) => {
              let x = node.x || 400
              let y = node.y || 150
              
              // Check against all existing nodes and previously added nodes
              let overlaps = true
              let attempts = 0
              
              while (overlaps && attempts < 100) {
                overlaps = updatedNodes.some(existing => {
                  const dx = Math.abs(existing.x - x)
                  const dy = Math.abs(existing.y - y)
                  return dx < nodeWidth && dy < nodeHeight
                })
                
                if (overlaps) {
                  // Try positioning below the overlapping node
                  y += nodeHeight + margin
                  
                  // If too far down, move to next column
                  if (y > 700) {
                    y = 150
                    x += nodeWidth + margin
                  }
                  attempts++
                }
              }
              
              // Add the new node with calculated position
              updatedNodes.push({
                id: node.id,
                type: node.type,
                name: node.name || node.checkType,
                checkType: node.checkType,
                x,
                y,
                config: node.config || {},
                connections: []
              })
            })
          }

          // Add new connections to existing and new nodes
          if (updates.connections && updates.connections.length > 0) {
            updatedNodes = updatedNodes.map(node => {
              const nodeConnections = updates.connections
                .filter((conn: any) => conn.from === node.id)
                .map((conn: any) => conn.to)
              
              if (nodeConnections.length > 0) {
                const existingConnections = node.connections || []
                const newUniqueConnections = nodeConnections.filter((c: string) => !existingConnections.includes(c))
                if (newUniqueConnections.length > 0) {
                  return { ...node, connections: [...existingConnections, ...newUniqueConnections] }
                }
              }
              return node
            })
          }

          return updatedNodes
        })

        setPromptMessage({ type: 'success', text: result.message })
        setTimeout(() => setPromptMessage(null), 3000)
      } else {
        setPromptMessage({ type: 'error', text: result.message || 'Failed to process request' })
      }
    } catch (error: any) {
      console.error('Error processing AI prompt:', error)
      setPromptMessage({ type: 'error', text: error.response?.data?.detail || error.message })
    } finally {
      setIsProcessingPrompt(false)
    }
  }

  // Canvas interaction handlers
  const handleNodeMouseDown = (e: React.MouseEvent, node: FlowNode) => {
    if (e.button === 0) {
      e.stopPropagation()
      setDraggedNode(node)
      const canvas = document.getElementById('flow-canvas')
      if (canvas) {
        const canvasRect = canvas.getBoundingClientRect()
        setDragOffset({
          x: e.clientX - canvasRect.left - node.x,
          y: e.clientY - canvasRect.top - node.y
        })
      }
    }
  }

  const handleCanvasMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setMousePos({ x, y })
    
    if (draggedNode) {
      setFlowNodes(prev => prev.map(n => 
        n.id === draggedNode.id ? { ...n, x: x - dragOffset.x, y: y - dragOffset.y } : n
      ))
    }
  }

  const handleCanvasMouseUp = () => {
    if (connectionStart) {
      setConnectionStart(null)
    }
    setDraggedNode(null)
  }

  const handleStartConnection = (e: React.MouseEvent, node: FlowNode) => {
    e.stopPropagation()
    setConnectionStart(node)
  }

  const handleEndConnection = (e: React.MouseEvent, targetNode: FlowNode) => {
    e.stopPropagation()
    
    if (connectionStart && connectionStart.id !== targetNode.id) {
      if (connectionStart.type === 'source' && targetNode.type === 'check') {
        setFlowNodes(prev => {
          const currentSourceNode = prev.find(n => n.id === connectionStart.id)
          if (currentSourceNode && !currentSourceNode.connections.includes(targetNode.id)) {
            return prev.map(n =>
              n.id === connectionStart.id
                ? { ...n, connections: [...n.connections, targetNode.id] }
                : n
            )
          }
          return prev
        })
      }
    }
    
    setConnectionStart(null)
  }

  const handleDeleteNode = (nodeId: string) => {
    // Remove the node and clean up all connections to it
    setFlowNodes(prev =>
      prev
        .filter(n => n.id !== nodeId)
        .map(n => ({
          ...n,
          connections: n.connections.filter(connId => connId !== nodeId)
        }))
    )
    if (selectedNode?.id === nodeId) {
      setSelectedNode(null)
      setShowCheckConfig(false)
    }
  }

  const handleDuplicateNode = (nodeId: string) => {
    setFlowNodes(prev => {
      const original = prev.find(n => n.id === nodeId)
      if (!original) return prev

      const newId = `${original.type}_${Date.now()}`
      const ruleName = original.config?.rule_name || original.config?.ruleName || original.name || ''
      const duplicate: FlowNode = {
        ...original,
        id: newId,
        name: ruleName ? `${ruleName} (copy)` : `${original.name} (copy)`,
        x: original.x + 30,
        y: original.y + 30,
        connections: [],
        config: original.config
          ? { ...original.config, rule_name: ruleName ? `${ruleName} (copy)` : '' }
          : {},
      }
      return [...prev, duplicate]
    })
  }

  const handleNodeClick = (node: FlowNode) => {
    setSelectedNode(node)
    if (node.type === 'check') {
      setCheckConfig(node.config || {})
      setShowCheckConfig(true)
      setShowSourceConfig(false)
    } else if (node.type === 'source') {
      setShowCheckConfig(false)
      setShowSourceConfig(true)
    }
  }

  const handleSelectSuggestedDataSource = async (dataSource: any) => {
    if (!activeWorkspaceId) return
    
    // Create a new source node with the selected data source configuration
    const newNode: FlowNode = {
      id: `source_${Date.now()}`,
      type: 'source',
      name: dataSource.name || dataSource.table_name,
      x: 150 + flowNodes.filter(n => n.type === 'source').length * 280,
      y: 100,
      config: {
        ...dataSource,
        id: dataSource.id,
        table_name: dataSource.table_name,
        schema_name: dataSource.schema_name,
        type: dataSource.connection_type
      },
      connections: []
    }
    
    // Add the selected data source to the flow
    const updatedNodes = [...flowNodes, newNode]
    setFlowNodes(updatedNodes)
    
    // If we have pending tasks, process them directly without re-prompting
    if (pendingTasks && pendingTasks.length > 0) {
      setPromptMessage({ type: 'info', text: `Added ${newNode.name}. Processing ${pendingTasks.length} check(s)...` })
      setIsProcessingPrompt(true)
      
      try {
        // Get available columns from the selected data source
        const availableColumns = dataSource.metadata?.columns || []
        const availableColumnNames = availableColumns.map((col: any) => 
          typeof col === 'string' ? col : col.column_name || col.name
        ).filter(Boolean)
        
        // Helper function to fuzzy match column names
        const fuzzyMatchColumn = (requestedCol: string): { matched: string | null, score: number } => {
          if (!requestedCol) return { matched: null, score: 0 }
          
          const requested = requestedCol.toLowerCase()
          let bestMatch = null
          let bestScore = 0
          
          for (const col of availableColumnNames) {
            const colLower = col.toLowerCase()
            
            // Exact match
            if (colLower === requested) {
              return { matched: col, score: 100 }
            }
            
            // Contains match
            if (colLower.includes(requested) || requested.includes(colLower)) {
              const score = Math.max(requested.length, colLower.length) / 
                           Math.min(requested.length, colLower.length) * 80
              if (score > bestScore) {
                bestScore = score
                bestMatch = col
              }
            }
            
            // Levenshtein-like similarity (simple version)
            const maxLen = Math.max(requested.length, colLower.length)
            let matches = 0
            for (let i = 0; i < Math.min(requested.length, colLower.length); i++) {
              if (requested[i] === colLower[i]) matches++
            }
            const score = (matches / maxLen) * 100
            if (score > bestScore && score > 60) {
              bestScore = score
              bestMatch = col
            }
          }
          
          return { matched: bestMatch, score: bestScore }
        }
        
        // Validate and correct column names in pending tasks
        const validatedTasks = pendingTasks.map((task: any) => {
          if (!task.columns || task.columns.length === 0) {
            return { ...task, validationError: 'No columns specified' }
          }
          
          const correctedColumns: string[] = []
          const invalidColumns: string[] = []
          const corrections: { from: string, to: string }[] = []
          
          for (const col of task.columns) {
            const { matched, score } = fuzzyMatchColumn(col)
            
            if (matched && score >= 70) {
              correctedColumns.push(matched)
              if (col.toLowerCase() !== matched.toLowerCase()) {
                corrections.push({ from: col, to: matched })
              }
            } else {
              invalidColumns.push(col)
            }
          }
          
          return {
            ...task,
            columns: correctedColumns.length > 0 ? correctedColumns : task.columns,
            invalidColumns,
            corrections,
            validationError: correctedColumns.length === 0 ? 
              `Columns not found: ${invalidColumns.join(', ')}` : null
          }
        })
        
        // Check if there are validation errors
        const tasksWithErrors = validatedTasks.filter((t: any) => t.validationError)
        
        if (tasksWithErrors.length > 0) {
          // Show clarification message
          const errorMessages = tasksWithErrors.map((t: any) => t.validationError).join('\n')
          const suggestions = `Available columns: ${availableColumnNames.join(', ')}`
          
          setPendingTasks(null)
          setPromptMessage({ 
            type: 'error', 
            text: `⚠️ Column validation failed:\n${errorMessages}\n\n${suggestions}` 
          })
          setIsProcessingPrompt(false)
          return
        }
        
        // Show corrections if any
        const allCorrections = validatedTasks.flatMap((t: any) => t.corrections || [])
        if (allCorrections.length > 0) {
          const correctionMsg = allCorrections.map((c: any) => `"${c.from}" → "${c.to}"`).join(', ')
          console.log(`✓ Auto-corrected columns: ${correctionMsg}`)
        }
        
        // Store corrections for success message
        const corrections = allCorrections
        
        // Process each validated task to create checks
        const newChecks: FlowNode[] = []
        const newConnections: { from: string, to: string }[] = []
        
        const nodeWidth = 220
        const nodeHeight = 120
        const margin = 30
        
        validatedTasks.forEach((task: any, idx: number) => {
          // Calculate non-overlapping position
          let x = 400
          let y = 150 + (idx * (nodeHeight + margin))
          
          let overlaps = true
          let attempts = 0
          
          while (overlaps && attempts < 100) {
            overlaps = [...updatedNodes, ...newChecks].some(existing => {
              const dx = Math.abs(existing.x - x)
              const dy = Math.abs(existing.y - y)
              return dx < nodeWidth && dy < nodeHeight
            })
            
            if (overlaps) {
              y += nodeHeight + margin
              if (y > 700) {
                y = 150
                x += nodeWidth + margin
              }
              attempts++
            }
          }
          
          const checkId = `check_${task.type}_${Date.now()}_${idx}`
          const columnsStr = task.columns?.join(', ') || ''
          
          newChecks.push({
            id: checkId,
            type: 'check',
            checkType: task.type,
            name: `${task.type.charAt(0).toUpperCase() + task.type.slice(1)} Check - ${columnsStr}`,
            x,
            y,
            config: {
              columns: task.columns || [],
              threshold: task.threshold || 90,
              validationType: task.validation_type || task.validationType || 'custom',
              ...(task.pattern && { pattern: task.pattern })
            },
            connections: []
          })
          
          // Create connection from source to check
          newConnections.push({
            from: newNode.id,
            to: checkId
          })
        })
        
        // Add new checks and update connections
        setFlowNodes(prev => {
          const updated = [...prev, ...newChecks]
          
          // Add connections
          return updated.map(node => {
            const nodeConns = newConnections
              .filter(conn => conn.from === node.id)
              .map(conn => conn.to)
            
            if (nodeConns.length > 0) {
              return {
                ...node,
                connections: [...(node.connections || []), ...nodeConns]
              }
            }
            return node
          })
        })
        
        setPendingTasks(null)
        
        // Build success message with corrections if any
        let successText = `✅ Added ${newNode.name} with ${newChecks.length} check(s)`
        if (corrections.length > 0) {
          const correctionText = corrections.map((c: any) => `"${c.from}" → "${c.to}"`).join(', ')
          successText += `\n📝 Auto-corrected: ${correctionText}`
        }
        
        setPromptMessage({ 
          type: 'success', 
          text: successText
        })
        setTimeout(() => setPromptMessage(null), 3000)
        
      } catch (error: any) {
        console.error('Error processing pending tasks:', error)
        setPromptMessage({ type: 'error', text: 'Failed to process checks' })
      } finally {
        setIsProcessingPrompt(false)
      }
    } else {
      // No pending tasks, just show success
      setPromptMessage({ type: 'success', text: `Added data source: ${newNode.name}` })
      setTimeout(() => setPromptMessage(null), 3000)
    }
  }

  const handleSaveSourceConfig = (config: any) => {
    if (selectedNode && selectedNode.type === 'source') {
      // Ensure required identifiers are present
      const id = config.dataset_id || config.data_source_id || config.id
      if (!id) {
        setSaveMessage('❌ Error: No dataset selected')
        setTimeout(() => setSaveMessage(''), 5000)
        return
      }

      const updatedNode = {
        ...selectedNode,
        config: config,
        name: config.dataset_name || config.physical_identifier || config.name || selectedNode.name,
      }

      setFlowNodes(prev => prev.map(n => n.id === selectedNode.id ? updatedNode : n))
      setSelectedNode(updatedNode)
      setSaveMessage('✅ Dataset configured')
      setTimeout(() => setSaveMessage(''), 3000)
    }
  }

  const handleSaveCheckConfig = useCallback((config?: any) => {
    if (selectedNode && selectedNode.type === 'check') {
      // Use passed config directly to avoid stale closure; fall back to checkConfig state
      const effectiveConfig = config && Object.keys(config).length > 0 ? config : checkConfig
      const nodeId = selectedNode.id
      
      // Update the node in the flow — use latest node from state, not stale closure
      setFlowNodes(prevNodes => 
        prevNodes.map(n => n.id === nodeId ? { ...n, config: effectiveConfig } : n)
      )
      
      // Update selected node with latest data
      setSelectedNode(prev => prev && prev.id === nodeId ? { ...prev, config: effectiveConfig } : prev)
      
      // Close the config panel
      setShowCheckConfig(false)
      
      // Show success message
      setSaveMessage('✅ Check configuration saved')
      setTimeout(() => setSaveMessage(''), 3000)
    }
  }, [selectedNode, checkConfig])

  return {
    // State
    flowId,
    flowName,
    setFlowName,
    flowDescription,
    setFlowDescription,
    flowNodes,
    setFlowNodes,
    selectedNode,
    setSelectedNode,
    activeTab,
    setActiveTab,
    showLibrary,
    setShowLibrary,
    selectedCategory,
    setSelectedCategory,
    draggedNode,
    connectionStart,
    mousePos,
    searchTerm,
    setSearchTerm,
    realDataSources,
    showCheckConfig,
    setShowCheckConfig,
    showSourceConfig,
    setShowSourceConfig,
    checkConfig,
    setCheckConfig,
    isProcessingPrompt,
    promptMessage,
    isSaving,
    isExecuting,
    saveMessage,
    saveStatus,
    flowExecutions,
    setFlowExecutions,
    selectedExecution,
    setSelectedExecution,
    selectedExecutionForReport,
    setSelectedExecutionForReport,
    currentExecution,
    // Handlers
    handleAddComponent,
    handleSaveFlow,
    handleExecuteFlow,
    handleAiPromptSubmit,
    handleNodeMouseDown,
    handleCanvasMouseMove,
    handleCanvasMouseUp,
    handleStartConnection,
    handleEndConnection,
    handleDeleteNode,
    handleDuplicateNode,
    handleNodeClick,
    handleSelectSuggestedDataSource,
    handleSaveSourceConfig,
    handleSaveCheckConfig,
  }
}
