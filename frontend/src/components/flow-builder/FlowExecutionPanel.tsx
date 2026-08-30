import { useState, useEffect } from 'react'
import * as React from 'react'
import { 
  Play, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Loader2, 
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Database,
  Shield,
  Target,
  GitBranch,
  XOctagon
} from 'lucide-react'
import { DocumentTextIcon } from '@heroicons/react/24/outline'
import flowService, { FlowExecution, ExecutionStatus, FlowNodeResult } from '../../services/flow'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import toast from 'react-hot-toast'

interface FlowExecutionPanelProps {
  flowId: string
  executions: FlowExecution[]
  currentExecution: FlowExecution | null
  onRefresh: () => void
  onViewReport?: (execution: FlowExecution) => void
}

export function FlowExecutionPanel({ 
  executions, 
  currentExecution,
  onRefresh,
  onViewReport
}: FlowExecutionPanelProps) {
  const { currentWorkspace } = useWorkspace()
  const [expandedExecution, setExpandedExecution] = useState<string | null>(null)
  const [nodeResults, setNodeResults] = useState<Record<string, FlowNodeResult[]>>({})
  const [loadingNodes, setLoadingNodes] = useState<Record<string, boolean>>({})
  const [cancellingExecutions, setCancellingExecutions] = useState<Set<string>>(new Set())
  const [currentTime, setCurrentTime] = useState(Date.now())

  // Ensure executions is always an array
  const executionsList = Array.isArray(executions) ? executions : []
  
  // Include currentExecution in the list if it's not already there
  const allExecutions = React.useMemo(() => {
    if (!currentExecution) return executionsList
    
    // Check if currentExecution is already in the list
    const exists = executionsList.some(e => e.id === currentExecution.id)
    if (exists) return executionsList
    
    // Add currentExecution at the beginning
    return [currentExecution, ...executionsList]
  }, [executionsList, currentExecution])
  
  // Debug logging
  useEffect(() => {
    console.log('FlowExecutionPanel - executions:', executions)
    console.log('FlowExecutionPanel - executionsList:', executionsList)
    console.log('FlowExecutionPanel - currentExecution:', currentExecution)
    console.log('FlowExecutionPanel - allExecutions:', allExecutions)
  }, [executions, executionsList, currentExecution, allExecutions])

  // Live timer for running executions
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(Date.now())
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // Auto-expand current execution
  useEffect(() => {
    if (currentExecution && currentExecution.status !== ExecutionStatus.COMPLETED && currentExecution.status !== ExecutionStatus.FAILED) {
      setExpandedExecution(currentExecution.id)
      loadNodeResults(currentExecution.id)
    }
  }, [currentExecution])

  const loadNodeResults = async (executionId: string) => {
    if (!currentWorkspace || loadingNodes[executionId]) return
    
    setLoadingNodes(prev => ({ ...prev, [executionId]: true }))
    try {
      const results = await flowService.getNodeResults(currentWorkspace?.workspace_id, executionId)
      setNodeResults(prev => ({ ...prev, [executionId]: results }))
    } catch (error) {
      console.error('Error loading node results:', error)
    } finally {
      setLoadingNodes(prev => ({ ...prev, [executionId]: false }))
    }
  }

  const toggleExecution = (executionId: string) => {
    if (expandedExecution === executionId) {
      setExpandedExecution(null)
    } else {
      setExpandedExecution(executionId)
      if (!nodeResults[executionId]) {
        loadNodeResults(executionId)
      }
    }
  }

  const getStatusIcon = (status: ExecutionStatus) => {
    switch (status) {
      case ExecutionStatus.COMPLETED:
        return <CheckCircle className="w-5 h-5 text-green-400" />
      case ExecutionStatus.WARNING:
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />
      case ExecutionStatus.RUNNING:
        return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
      case ExecutionStatus.PENDING:
        return <Clock className="w-5 h-5 text-yellow-400" />
      case ExecutionStatus.FAILED:
        return <XCircle className="w-5 h-5 text-red-400" />
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />
    }
  }

  const getStatusBadge = (status: ExecutionStatus) => {
    const baseClasses = "px-2 py-1 rounded text-xs font-medium"
    switch (status) {
      case ExecutionStatus.COMPLETED:
        return <span className={`${baseClasses} bg-green-500/20 text-green-400`}>Completed</span>
      case ExecutionStatus.WARNING:
        return <span className={`${baseClasses} bg-yellow-500/20 text-yellow-400`}>Warning</span>
      case ExecutionStatus.RUNNING:
        return <span className={`${baseClasses} bg-blue-500/20 text-blue-400`}>Running</span>
      case ExecutionStatus.PENDING:
        return <span className={`${baseClasses} bg-yellow-500/20 text-yellow-400`}>Pending</span>
      case ExecutionStatus.FAILED:
        return <span className={`${baseClasses} bg-red-500/20 text-red-400`}>Failed</span>
      default:
        return <span className={`${baseClasses} bg-gray-500/20 text-gray-400`}>{status}</span>
    }
  }

  const getNodeStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
      case 'passed':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-400" />
      case 'running':
        return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
      case 'pending':
        return <Clock className="w-4 h-4 text-gray-400" />
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-400" />
      case 'skipped':
        return <AlertCircle className="w-4 h-4 text-yellow-400" />
      default:
        return <Clock className="w-4 h-4 text-gray-400" />
    }
  }

  const getNodeTypeIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'source':
        return <Database className="w-4 h-4 text-blue-400" />
      case 'check':
      case 'completeness':
      case 'validity':
        return <Shield className="w-4 h-4 text-green-400" />
      case 'accuracy':
      case 'consistency':
        return <Target className="w-4 h-4 text-purple-400" />
      case 'reconciliation':
        return <GitBranch className="w-4 h-4 text-emerald-400" />
      default:
        return <CheckCircle className="w-4 h-4 text-gray-400" />
    }
  }

  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'N/A'
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const minutes = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${minutes}m ${secs}s`
  }

  const calculateElapsedTime = (execution: FlowExecution): number => {
    if (!execution.started_at) return 0
    
    const startTime = new Date(execution.started_at).getTime()
    const endTime = execution.completed_at 
      ? new Date(execution.completed_at).getTime() 
      : currentTime
    
    return Math.floor((endTime - startTime) / 1000)
  }

  const handleCancelExecution = async (executionId: string) => {
    if (!currentWorkspace) return
    
    if (!confirm('Are you sure you want to cancel this execution?')) return
    
    setCancellingExecutions(prev => new Set(prev).add(executionId))
    try {
      await flowService.cancelExecution(currentWorkspace?.workspace_id, executionId)
      onRefresh()
    } catch (error: any) {
      console.error('Error cancelling execution:', error)
      toast.error(error.message || 'Failed to cancel execution')
    } finally {
      setCancellingExecutions(prev => {
        const next = new Set(prev)
        next.delete(executionId)
        return next
      })
    }
  }

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return 'N/A'
    const date = new Date(timestamp)
    return date.toLocaleString()
  }

  if (allExecutions.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="glass p-12 text-center rounded-lg">
          <Play className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-300 mb-2">No Executions Yet</h3>
          <p className="text-gray-500">Click the Execute button to run your flow</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-300">Execution History</h2>
        <button 
          onClick={onRefresh}
          className="px-3 py-1 bg-dark-800 hover:bg-dark-700 rounded text-gray-300 flex items-center space-x-1 text-xs"
        >
          <Loader2 className="w-3 h-3" />
          <span>Refresh</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3">
        {allExecutions.map((execution) => {
          const isExpanded = expandedExecution === execution.id
          const results = nodeResults[execution.id] || []
          const isLoading = loadingNodes[execution.id]

          return (
            <div key={execution.id} className="glass rounded-lg overflow-hidden">
              {/* Execution Header */}
              <div className="p-4">
                <div className="flex items-center justify-between">
                  <div 
                    className="flex-1 cursor-pointer hover:bg-dark-800/30 -m-2 p-2 rounded transition-colors"
                    onClick={() => toggleExecution(execution.id)}
                  >
                  <div className="flex items-center space-x-3">
                    {isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                    {getStatusIcon(execution.status)}
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-medium text-gray-300">
                          Execution #{execution.id.slice(0, 8)}
                        </span>
                        {getStatusBadge(execution.status)}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {formatTimestamp(execution.started_at)}
                      </div>
                    </div>
                  </div>

                    <div className="flex items-center space-x-6 text-xs">
                      <div className="text-center">
                        <div className="text-gray-500">Duration</div>
                        <div className="text-gray-300 font-medium">
                          {execution.status === ExecutionStatus.RUNNING ? (
                            <span className="text-blue-400 font-mono">
                              {formatDuration(calculateElapsedTime(execution))}
                            </span>
                          ) : (
                            formatDuration(execution.duration_seconds ?? execution.execution_time_seconds)
                          )}
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-500">Nodes</div>
                        <div className="text-gray-300 font-medium">
                          {execution.nodes_executed}
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-500">Passed</div>
                        <div className="text-green-400 font-medium">{execution.nodes_passed}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-500">Failed</div>
                        <div className="text-red-400 font-medium">{execution.nodes_failed}</div>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    {execution.status === ExecutionStatus.RUNNING && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleCancelExecution(execution.id)
                        }}
                        disabled={cancellingExecutions.has(execution.id)}
                        className="px-3 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                        title="Cancel execution"
                      >
                        {cancellingExecutions.has(execution.id) ? (
                          <><Loader2 className="w-4 h-4 animate-spin" /> Cancelling...</>
                        ) : (
                          <><XOctagon className="w-4 h-4" /> Cancel</>
                        )}
                      </button>
                    )}
                    {onViewReport && (execution.status === ExecutionStatus.COMPLETED || execution.status === ExecutionStatus.FAILED) && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onViewReport(execution)
                        }}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                      >
                        <DocumentTextIcon className="w-4 h-4" />
                        View Report
                      </button>
                    )}
                  </div>
                </div>

                {execution.error_message && (
                  <div className="mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded text-xs">
                    <div className="flex items-start space-x-2">
                      <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                      <div className="flex-1">
                        <strong className="text-red-400">Error:</strong> 
                        <span className="text-red-300 ml-1">{execution.error_message}</span>
                        
                        {/* Show validation error details if available */}
                        {execution.error_details?.errors && Array.isArray(execution.error_details.errors) && (
                          <div className="mt-2 space-y-1">
                            <div className="text-red-400 font-medium">Validation Errors:</div>
                            {execution.error_details.errors.map((error: any, idx: number) => (
                              <div key={idx} className="pl-3 text-red-300">
                                • {error.message || error}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Execution Details - Node Results */}
              {isExpanded && (
                <div className="border-t border-dark-800 p-4 bg-dark-900/30">
                  {isLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
                      <span className="ml-2 text-gray-500">Loading node results...</span>
                    </div>
                  ) : execution.status === 'failed' && execution.error_message ? (
                    <div className="py-8 px-4">
                      <div className="text-center mb-4">
                        <XCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
                        <h4 className="text-lg font-medium text-red-400 mb-2">Execution Failed</h4>
                        <p className="text-sm text-gray-400">
                          The flow failed validation before any nodes were executed
                        </p>
                      </div>
                      
                      {/* Show detailed validation errors */}
                      {execution.error_details?.errors && Array.isArray(execution.error_details.errors) && (
                        <div className="bg-dark-800/50 border border-red-500/30 rounded-lg p-4">
                          <h5 className="text-sm font-medium text-red-400 mb-3">Issues Found:</h5>
                          <ul className="space-y-2">
                            {execution.error_details.errors.map((error: any, idx: number) => (
                              <li key={idx} className="text-sm text-gray-300 flex items-start space-x-2">
                                <span className="text-red-400 mt-1">•</span>
                                <span>{error.message || error}</span>
                              </li>
                            ))}
                          </ul>
                          
                          <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded text-xs text-blue-300">
                            <strong>💡 Tip:</strong> Make sure your source nodes are configured with data sources and have columns selected.
                          </div>
                        </div>
                      )}
                    </div>
                  ) : results.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      No node execution details available
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <h4 className="text-sm font-medium text-gray-400 mb-3">Node Execution Details</h4>
                      {results
                        .sort((a, b) => a.execution_order - b.execution_order)
                        .map((node) => {
                          const rd = node.result_data || {}
                          const isSource = (rd.node_type === 'source' || rd.source_type)
                          const isCheck = !isSource

                          // Node name: source → source_name/data_source_name, check → node_label/ruleName/check_type
                          const nodeName = isSource
                            ? (rd.source_name || rd.data_source_name || rd.file_name || node.node_id)
                            : (rd.node_label || rd.check_type || node.node_id)

                          // Check status badge
                          const checkStatus = rd.check_status as string | undefined
                          const statusBadge = checkStatus === 'PASS'
                            ? { text: 'PASS', cls: 'bg-green-500/20 text-green-400' }
                            : checkStatus === 'WARN'
                              ? { text: 'WARN', cls: 'bg-yellow-500/20 text-yellow-400' }
                              : checkStatus === 'FAIL'
                                ? { text: 'FAIL', cls: 'bg-red-500/20 text-red-400' }
                                : null

                          return (
                          <div 
                            key={node.id} 
                            className="glass p-3 rounded-lg flex items-start space-x-3"
                          >
                            <div className="flex-shrink-0 mt-0.5">
                              {getNodeStatusIcon(node.status)}
                            </div>
                            <div className="flex-shrink-0 mt-0.5">
                              {getNodeTypeIcon(rd.node_type || (isSource ? 'source' : 'check'))}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between">
                                <div className="flex-1">
                                  <div className="flex items-center space-x-2">
                                    <div className="text-sm font-medium text-gray-300">
                                      {nodeName}
                                    </div>
                                    {isCheck && rd.check_type && (
                                      <span className="px-2 py-0.5 bg-primary-500/20 text-primary-400 rounded text-xs font-medium">
                                        {rd.check_type}
                                      </span>
                                    )}
                                    {statusBadge && (
                                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusBadge.cls}`}>
                                        {statusBadge.text}
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-xs text-gray-500 mt-1">
                                    {isSource ? 'Source' : 'Check'} • Order: {node.execution_order}
                                    {rd.dataset && (
                                      <span> • Dataset: {rd.dataset}</span>
                                    )}
                                    {!rd.dataset && rd.table_name && (
                                      <span> • Table: {rd.table_name}</span>
                                    )}
                                  </div>
                                  {/* Show threshold info for check nodes */}
                                  {isCheck && rd.threshold_pass !== undefined && (
                                    <div className="mt-1 flex items-center gap-2 text-xs">
                                      <span className="text-gray-500">Score:</span>
                                      <span className={
                                        checkStatus === 'PASS' ? 'text-green-400 font-medium' :
                                        checkStatus === 'WARN' ? 'text-yellow-400 font-medium' :
                                        'text-red-400 font-medium'
                                      }>
                                        {typeof rd.pass_rate === 'number' ? rd.pass_rate.toFixed(2) : rd.pass_rate}%
                                      </span>
                                      <span className="text-gray-600">|</span>
                                      <span className="text-gray-500">Pass ≥ {rd.threshold_pass}%</span>
                                      {rd.threshold_warn !== null && rd.threshold_warn !== undefined && (
                                        <>
                                          <span className="text-gray-600">|</span>
                                          <span className="text-gray-500">Warn ≥ {rd.threshold_warn}%</span>
                                        </>
                                      )}
                                    </div>
                                  )}
                                  {/* Group-by breakdown for group completeness */}
                                  {isCheck && rd.check_mode === 'group' && Array.isArray(rd.group_results) && rd.group_results.length > 0 && (
                                    <div className="mt-1 text-xs space-y-0.5">
                                      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                                        {rd.group_results.map((grp: any, i: number) => {
                                          const label = Object.values(grp.group_key as Record<string, unknown> || {}).join(', ') || `Group ${i + 1}`
                                          const rate = typeof grp.pass_rate === 'number' ? grp.pass_rate.toFixed(1) : grp.pass_rate
                                          const cls = grp.check_status === 'PASS' ? 'text-green-400' : grp.check_status === 'WARN' ? 'text-yellow-400' : 'text-red-400'
                                          return (
                                            <span key={i} className={cls}>
                                              {label}: {grp.passed_rows}/{grp.total_rows} ({rate}%)
                                            </span>
                                          )
                                        })}
                                      </div>
                                      {(() => {
                                        const failing = rd.group_results.filter((g: any) => g.check_status !== 'PASS')
                                        if (failing.length === 0) return null
                                        const names = failing.map((g: any) => Object.values(g.group_key as Record<string, unknown> || {}).join(', ')).join(', ')
                                        return (
                                          <div className="text-red-400">
                                            At {rd.threshold_pass}%, {names} {failing.length === 1 ? 'fails' : 'fail'}
                                          </div>
                                        )
                                      })()}
                                    </div>
                                  )}
                                  {/* Show columns being checked */}
                                  {rd.columns && Array.isArray(rd.columns) && rd.columns.length > 0 && (
                                    <div className="mt-1 flex flex-wrap gap-1">
                                      <span className="text-xs text-gray-500">Columns:</span>
                                      {rd.columns.slice(0, 5).map((col: string, idx: number) => (
                                        <span key={idx} className="px-1.5 py-0.5 bg-dark-700 text-gray-400 rounded text-xs">
                                          {col}
                                        </span>
                                      ))}
                                      {rd.columns.length > 5 && (
                                        <span className="text-xs text-gray-500">+{rd.columns.length - 5} more</span>
                                      )}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right text-xs">
                                  {node.execution_time_seconds !== undefined && (
                                    <div className="text-gray-400">
                                      {formatDuration(node.execution_time_seconds)}
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Node metrics */}
                              {isCheck && rd.rows_scanned !== undefined && (
                                <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                                  <div className="bg-dark-800/50 rounded px-2 py-1">
                                    <div className="text-gray-500">Scanned</div>
                                    <div className="text-gray-300 font-medium">
                                      {rd.rows_scanned.toLocaleString()}
                                    </div>
                                  </div>
                                  <div className="bg-green-500/10 rounded px-2 py-1">
                                    <div className="text-gray-500">Passed</div>
                                    <div className="text-green-400 font-medium">
                                      {(rd.rows_passed ?? 0).toLocaleString()}
                                    </div>
                                  </div>
                                  <div className="bg-red-500/10 rounded px-2 py-1">
                                    <div className="text-gray-500">Failed</div>
                                    <div className="text-red-400 font-medium">
                                      {(rd.rows_failed ?? 0).toLocaleString()}
                                    </div>
                                  </div>
                                </div>
                              )}
                              {/* Source node metrics */}
                              {isSource && rd.row_count !== undefined && (
                                <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                                  <div className="bg-dark-800/50 rounded px-2 py-1">
                                    <div className="text-gray-500">Rows</div>
                                    <div className="text-gray-300 font-medium">
                                      {rd.row_count.toLocaleString()}
                                    </div>
                                  </div>
                                  {rd.columns && Array.isArray(rd.columns) && (
                                    <div className="bg-dark-800/50 rounded px-2 py-1">
                                      <div className="text-gray-500">Columns</div>
                                      <div className="text-gray-300 font-medium">
                                        {rd.columns.length}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                              {/* Legacy metrics fallback */}
                              {!isCheck && !isSource && node.result_data && (
                                <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                                  {rd.records_processed !== undefined && (
                                    <div className="bg-dark-800/50 rounded px-2 py-1">
                                      <div className="text-gray-500">Processed</div>
                                      <div className="text-gray-300 font-medium">
                                        {rd.records_processed.toLocaleString()}
                                      </div>
                                    </div>
                                  )}
                                  {rd.records_passed !== undefined && (
                                    <div className="bg-green-500/10 rounded px-2 py-1">
                                      <div className="text-gray-500">Passed</div>
                                      <div className="text-green-400 font-medium">
                                        {rd.records_passed.toLocaleString()}
                                      </div>
                                    </div>
                                  )}
                                  {rd.records_failed !== undefined && (
                                    <div className="bg-red-500/10 rounded px-2 py-1">
                                      <div className="text-gray-500">Failed</div>
                                      <div className="text-red-400 font-medium">
                                        {rd.records_failed.toLocaleString()}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Error message */}
                              {node.error_message && (
                                <div className="mt-2 p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400">
                                  {node.error_message}
                                </div>
                              )}
                            </div>
                          </div>
                          )
                        })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
