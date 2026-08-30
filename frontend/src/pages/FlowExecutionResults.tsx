/**
 * FlowExecutionResults - View flow execution details and results
 */
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  Loader2,
  PlayCircle,
  Calendar,
  User,
  GitBranch,
} from 'lucide-react'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { useTenantScopedPath } from '../hooks/useTenantScopedPath'
import flowService, {
  FlowExecution,
  FlowNodeResult,
  ExecutionStatus,
  ExecutionTrigger,
} from '../services/flow'

export default function FlowExecutionResults() {
  const { executionId, workspace_id: urlWorkspaceId } = useParams<{ executionId: string; workspace_id?: string }>()
  const navigate = useNavigate()
  const { currentWorkspace } = useWorkspace()
  const activeWorkspaceId = urlWorkspaceId || currentWorkspace?.workspace_id
  const { wsPath } = useTenantScopedPath()

  const [execution, setExecution] = useState<FlowExecution | null>(null)
  const [nodeResults, setNodeResults] = useState<FlowNodeResult[]>([])
  const [loading, setLoading] = useState(true)
  const [polling, setPolling] = useState(false)

  useEffect(() => {
    if (activeWorkspaceId && executionId) {
      loadExecutionData()
    }
  }, [currentWorkspace, executionId])

  useEffect(() => {
    // Poll for updates if execution is running
    if (execution?.status === ExecutionStatus.RUNNING || execution?.status === ExecutionStatus.PENDING) {
      setPolling(true)
      const interval = setInterval(() => {
        loadExecutionData(true)
      }, 3000) // Poll every 3 seconds

      return () => {
        clearInterval(interval)
        setPolling(false)
      }
    }
  }, [execution?.status])

  const loadExecutionData = async (silent = false) => {
    if (!activeWorkspaceId || !executionId) return

    if (!silent) setLoading(true)

    try {
      const [execData, nodesData] = await Promise.all([
        flowService.getExecution(activeWorkspaceId, executionId),
        flowService.getNodeResults(activeWorkspaceId, executionId),
      ])

      setExecution(execData)
      setNodeResults(nodesData.sort((a, b) => a.execution_order - b.execution_order))
    } catch (error) {
      console.error('Error loading execution data:', error)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const getStatusIcon = (status: ExecutionStatus) => {
    switch (status) {
      case ExecutionStatus.COMPLETED:
        return <CheckCircle className="w-5 h-5 text-green-400" />
      case ExecutionStatus.FAILED:
        return <XCircle className="w-5 h-5 text-red-400" />
      case ExecutionStatus.RUNNING:
        return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
      case ExecutionStatus.PENDING:
        return <Clock className="w-5 h-5 text-yellow-400" />
      case ExecutionStatus.CANCELLED:
        return <AlertCircle className="w-5 h-5 text-gray-400" />
      default:
        return <Clock className="w-5 h-5 text-gray-400" />
    }
  }

  const getStatusBadge = (status: ExecutionStatus) => {
    const styles = {
      pending: 'bg-yellow-500/20 text-yellow-400',
      running: 'bg-blue-500/20 text-blue-400',
      completed: 'bg-green-500/20 text-green-400',
      failed: 'bg-red-500/20 text-red-400',
      cancelled: 'bg-gray-500/20 text-gray-400',
    }
    return (
      <span className={`px-3 py-1 rounded text-sm font-medium ${styles[status]}`}>
        {status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown'}
      </span>
    )
  }

  const getTriggerIcon = (trigger: ExecutionTrigger) => {
    switch (trigger) {
      case ExecutionTrigger.MANUAL:
        return <User className="w-4 h-4" />
      case ExecutionTrigger.SCHEDULED:
        return <Calendar className="w-4 h-4" />
      case ExecutionTrigger.API:
        return <GitBranch className="w-4 h-4" />
      default:
        return <PlayCircle className="w-4 h-4" />
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }

  if (!execution) {
    return (
      <div className="p-6">
        <div className="glass p-12 text-center rounded-lg">
          <AlertCircle className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-300 mb-2">Execution Not Found</h3>
          <p className="text-gray-500 mb-6">The execution you're looking for doesn't exist</p>
          <button onClick={() => navigate(activeWorkspaceId ? wsPath(activeWorkspaceId, '/flows') : '/hub/flows')} className="btn-primary">
            Back to Flows
          </button>
        </div>
      </div>
    )
  }

  const successRate =
    execution.nodes_executed > 0
      ? ((execution.nodes_passed / execution.nodes_executed) * 100).toFixed(1)
      : '0.0'

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => navigate(activeWorkspaceId ? wsPath(activeWorkspaceId, '/flows') : '/hub/flows')}
          className="flex items-center space-x-2 text-gray-400 hover:text-primary-400 mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Flows</span>
        </button>

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold gradient-text mb-2">Flow Execution Results</h1>
            <p className="text-gray-400">Execution ID: {execution.id}</p>
          </div>
          <div className="flex items-center space-x-3">
            {polling && (
              <span className="text-xs text-blue-400 flex items-center space-x-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Live updates</span>
              </span>
            )}
            {getStatusBadge(execution.status)}
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Status</span>
            {getStatusIcon(execution.status)}
          </div>
          <div className="text-2xl font-bold text-gray-200">
            {execution.status ? execution.status.charAt(0).toUpperCase() + execution.status.slice(1) : 'Unknown'}
          </div>
        </div>

        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Success Rate</span>
            <CheckCircle className="w-5 h-5 text-green-400" />
          </div>
          <div className="text-2xl font-bold text-green-400">{successRate}%</div>
          <div className="text-xs text-gray-500 mt-1">
            {execution.nodes_passed} / {execution.nodes_executed} nodes passed
          </div>
        </div>

        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Execution Time</span>
            <Clock className="w-5 h-5 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-blue-400">
            {execution.execution_time_seconds
              ? `${execution.execution_time_seconds.toFixed(1)}s`
              : '-'}
          </div>
        </div>

        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Trigger</span>
            {getTriggerIcon(execution.trigger)}
          </div>
          <div className="text-2xl font-bold text-gray-200">
            {execution.trigger ? execution.trigger.charAt(0).toUpperCase() + execution.trigger.slice(1) : 'Unknown'}
          </div>
        </div>
      </div>

      {/* Execution Timeline */}
      <div className="glass p-6 rounded-lg mb-6">
        <h2 className="text-lg font-semibold mb-4">Execution Timeline</h2>
        <div className="space-y-2 text-sm">
          {execution.started_at && (
            <div className="flex items-center space-x-3">
              <PlayCircle className="w-4 h-4 text-blue-400" />
              <span className="text-gray-400">Started:</span>
              <span className="text-gray-200">{new Date(execution.started_at).toLocaleString()}</span>
            </div>
          )}
          {execution.completed_at && (
            <div className="flex items-center space-x-3">
              <CheckCircle className="w-4 h-4 text-green-400" />
              <span className="text-gray-400">Completed:</span>
              <span className="text-gray-200">
                {new Date(execution.completed_at).toLocaleString()}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Node Results */}
      <div className="glass p-6 rounded-lg">
        <h2 className="text-lg font-semibold mb-4">Node Results</h2>

        {nodeResults.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Clock className="w-12 h-12 mx-auto mb-3 text-gray-600" />
            <p>No node results available yet</p>
          </div>
        ) : (
          <div className="space-y-3">
            {nodeResults.map((nodeResult, index) => (
              <div
                key={nodeResult.id}
                className="glass p-4 rounded-lg border border-dark-700 hover:border-primary-500/30 transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-3 flex-1">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-dark-800 text-gray-400 text-sm font-medium flex-shrink-0">
                      {index + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-3 mb-2">
                        <h3 className="font-medium text-gray-200">{nodeResult.node_id}</h3>
                        {getStatusBadge(nodeResult.status)}
                      </div>

                      {nodeResult.execution_time_seconds !== undefined && (
                        <div className="text-xs text-gray-500 mb-2">
                          Execution time: {nodeResult.execution_time_seconds.toFixed(2)}s
                        </div>
                      )}

                      {(nodeResult.error_message || nodeResult.error_details) && (
                        <div className="mt-2 p-3 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-400">
                          <div className="flex items-start space-x-2">
                            <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                            <div className="flex-1">
                              {nodeResult.error_message ? (
                                <span>{nodeResult.error_message}</span>
                              ) : nodeResult.error_details ? (
                                <div>
                                  <div className="font-semibold mb-1">
                                    {nodeResult.error_details.error_type || 'Error'}
                                  </div>
                                  {nodeResult.error_details.message && (
                                    <div className="text-xs text-red-300 mt-1">{nodeResult.error_details.message}</div>
                                  )}
                                  {nodeResult.error_details.traceback && (
                                    <details className="mt-2">
                                      <summary className="cursor-pointer text-xs text-red-300 hover:text-red-200">View stack trace</summary>
                                      <pre className="mt-2 p-2 bg-dark-900 rounded text-xs text-gray-400 overflow-x-auto max-h-48">
                                        {nodeResult.error_details.traceback}
                                      </pre>
                                    </details>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      )}

                      {nodeResult.result_data && Object.keys(nodeResult.result_data).length > 0 && (
                        <details className="mt-2">
                          <summary className="cursor-pointer text-xs text-primary-400 hover:text-primary-300">
                            View result data
                          </summary>
                          <pre className="mt-2 p-3 bg-dark-900 rounded text-xs text-gray-400 overflow-x-auto">
                            {JSON.stringify(nodeResult.result_data, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center ml-4">
                    {getStatusIcon(nodeResult.status)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Error Message (if any) */}
      {(execution.error_message || execution.error_details) && (
        <div className="glass p-6 rounded-lg mt-6 border border-red-500/30">
          <div className="flex items-start space-x-3">
            <XCircle className="w-6 h-6 text-red-400 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-red-400 mb-2">Execution Error</h3>
              {execution.error_message ? (
                <p className="text-gray-300 mb-3">{execution.error_message}</p>
              ) : execution.error_details ? (
                <div className="text-gray-300 mb-3">
                  <div className="font-semibold">{execution.error_details.error_type || 'Error'}</div>
                  {execution.error_details.message && <div className="text-sm mt-1">{execution.error_details.message}</div>}
                </div>
              ) : null}
              
              {/* Show detailed validation errors if available */}
              {execution.error_details?.errors && Array.isArray(execution.error_details.errors) && (
                <div className="mt-4">
                  <h4 className="text-sm font-semibold text-gray-400 mb-2">Validation Errors:</h4>
                  <ul className="space-y-2">
                    {execution.error_details.errors.map((error: any, index: number) => (
                      <li key={index} className="text-sm text-gray-400 bg-dark-900/50 p-3 rounded border border-dark-700">
                        <span className="text-red-400 font-medium">{error.type || 'Error'}:</span> {error.message}
                        {error.node_id && <span className="text-gray-500 ml-2">(Node: {error.node_id})</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
