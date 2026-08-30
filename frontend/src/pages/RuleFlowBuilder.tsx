import { useNavigate, useParams } from 'react-router-dom'
import { useEffect, useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listDatasets } from '../services/datasetService'
import type { DatasetOption } from '../components/flow-builder/shared/DatasetPicker'
import {
  Database,
  Play,
  Download,
  ArrowLeft,
  Loader2,
  FileBarChart,
  History,
  GitBranch,
  CheckCircle,
  Shield,
  Target,
  BarChart3,
  Clock,
} from 'lucide-react'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { useTenantScopedPath } from '../hooks/useTenantScopedPath'
import { useFlowBuilder } from '../components/flow-builder/useFlowBuilder'
import flowService from '../services/flow'
import { AIFlowPrompt } from '../components/flow-builder/AIFlowPrompt'
import { ComponentLibrary } from '../components/flow-builder/ComponentLibrary'
import { FlowCanvas } from '../components/flow-builder/FlowCanvas'
import { CheckConfigPanel } from '../components/flow-builder/CheckConfigPanel'
import { DatasetConfigPanel } from '../components/flow-builder/DatasetConfigPanel'
import { FlowExecutionPanel } from '../components/flow-builder/FlowExecutionPanel'
import { DataAssetsPanel } from '../components/flow-builder/DataAssetsPanel'
import { DQCheck } from '../components/flow-builder/types'
import { generateExecutionReportPDF } from '../utils/pdfExport'
import { FlowScheduleModal } from '../components/flow-builder/FlowScheduleModal'
import toast from 'react-hot-toast'

// Constants for component library
const COMPONENT_LIBRARY: any[] = [
  { id: 'dataset', type: 'dataset', category: 'source', name: 'Dataset', icon: Database, description: 'Add a dataset to the flow', color: 'bg-primary-500' },
]

const DQ_CHECK_LIBRARY: DQCheck[] = [
  { id: 'completeness', type: 'completeness', category: 'structural', name: 'Completeness', icon: CheckCircle, description: 'Required data must exist', color: 'bg-green-500' },
  { id: 'validity', type: 'validity', category: 'structural', name: 'Validity', icon: Shield, description: 'Values follow allowed formats', color: 'bg-blue-500' },
  { id: 'conformity', type: 'conformity', category: 'structural', name: 'Conformity', icon: Target, description: 'Same concept, same format', color: 'bg-purple-500' },
  { id: 'uniqueness', type: 'uniqueness', category: 'structural', name: 'Uniqueness', icon: CheckCircle, description: 'No duplicates expected', color: 'bg-cyan-500' },
  { id: 'accuracy', type: 'accuracy', category: 'semantic', name: 'Accuracy', icon: Target, description: 'Compare to golden source', color: 'bg-amber-500' },
  { id: 'consistency', type: 'consistency', category: 'semantic', name: 'Consistency', icon: GitBranch, description: 'Field coherence checks', color: 'bg-violet-500' },
  { id: 'timeliness', type: 'timeliness', category: 'structural', name: 'Timeliness', icon: History, description: 'Data arrives on time', color: 'bg-orange-500' },
  { id: 'reconciliation', type: 'reconciliation', category: 'reconciliation', name: 'Reconciliation', icon: GitBranch, description: 'Source vs target parity', color: 'bg-emerald-500' },
]

export default function RuleFlowBuilder() {
  const navigate = useNavigate()
  const { workspace_id: urlWorkspaceId } = useParams()
  const { currentWorkspace } = useWorkspace()
  const workspaceId = urlWorkspaceId || currentWorkspace?.workspace_id || ''
  const { wsPath } = useTenantScopedPath()

  // Fetch datasets for reference pickers in CheckConfigPanel
  const { data: datasetsResp, isLoading: loadingDatasets } = useQuery({
    queryKey: ['datasets', workspaceId],
    queryFn: () => listDatasets(workspaceId, { page_size: 100, status: 'active' }),
    enabled: !!workspaceId,
    staleTime: 60_000,
  })
  const availableDatasets = useMemo<DatasetOption[]>(
    () =>
      (datasetsResp?.items ?? []).map((d) => ({
        id: d.dataset_id,
        name: d.dataset_name,
        description: d.data_source_name ?? undefined,
      })),
    [datasetsResp],
  )

  // Local state for report node results
  const [reportNodeResults, setReportNodeResults] = useState<any[]>([])
  const [loadingReportData, setLoadingReportData] = useState(false)
  const [hasAutoLoadedReport, setHasAutoLoadedReport] = useState(false)
  const [showScheduleModal, setShowScheduleModal] = useState(false)

  const {
    // Flow state
    flowId,
    flowName,
    setFlowName,
    flowDescription,
    setFlowDescription,
    flowNodes,
    setFlowNodes,
    selectedNode,
    activeTab,
    setActiveTab,
    
    // UI state
    showLibrary,
    setShowLibrary,
    selectedCategory,
    setSelectedCategory,
    showCheckConfig,
    setShowCheckConfig,
    showSourceConfig,
    setShowSourceConfig,
    checkConfig,
    setCheckConfig,
    
    // Canvas interaction
    draggedNode,
    connectionStart,
    mousePos,
    
    // Data
    // (realDataSources still available from hook if needed for AI prompt)
    
    // Save/Execute state
    isExecuting,
    saveMessage,
    saveStatus,
    currentExecution,
    selectedExecutionForReport,
    setSelectedExecutionForReport,
    
    // AI prompt state
    isProcessingPrompt,
    promptMessage,
    
    // Executions
    flowExecutions,
    setFlowExecutions,
    
    // Handlers
    handleAddComponent,
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
  } = useFlowBuilder()

  // Local data for UI
  const categories = [
    { id: 'all', name: 'All Components', icon: GitBranch },
    { id: 'source', name: 'Datasets', icon: Database },
    { id: 'structural', name: 'Structural', icon: CheckCircle },
    { id: 'semantic', name: 'Semantic', icon: Target },
    { id: 'statistical', name: 'Statistical', icon: BarChart3 },
    { id: 'governance', name: 'Governance', icon: Shield },
    { id: 'reconciliation', name: 'Reconciliation', icon: GitBranch },
  ]

  const allChecks = [...COMPONENT_LIBRARY, ...DQ_CHECK_LIBRARY]
  const filteredChecks: any[] = selectedCategory === 'all' 
    ? allChecks 
    : allChecks.filter((c: any) => c.category === selectedCategory)
  // Auto-load latest execution when Reports tab is opened
  useEffect(() => {
    if (activeTab === 'reports' && !selectedExecutionForReport && !hasAutoLoadedReport && Array.isArray(flowExecutions) && flowExecutions.length > 0) {
      console.log('📊 Auto-loading latest execution for report')
      setSelectedExecutionForReport(flowExecutions[0])
      setHasAutoLoadedReport(true)
    }
  }, [activeTab, selectedExecutionForReport, flowExecutions, hasAutoLoadedReport])

  // Load node results when execution is selected for report
  useEffect(() => {
    const loadNodeResults = async () => {
      if (selectedExecutionForReport && workspaceId) {
        setLoadingReportData(true)
        try {
          const results = await flowService.getNodeResults(
            workspaceId,
            selectedExecutionForReport.id
          )
          setReportNodeResults(Array.isArray(results) ? results : [])
        } catch (error) {
          console.error('Error loading node results for report:', error)
          setReportNodeResults([])
        } finally {
          setLoadingReportData(false)
        }
      } else {
        setReportNodeResults([])
      }
    }
    loadNodeResults()
  }, [selectedExecutionForReport, workspaceId])
  // Poll executions when on Runs tab
  useEffect(() => {
    console.log('🔄 Runs tab useEffect triggered:', { activeTab, flowId, hasOrg: !!workspaceId, executionsCount: flowExecutions?.length })
    
    if (activeTab === 'runs' && flowId && workspaceId) {
      console.log('🔄 Runs tab active - loading executions for flow:', flowId)
      
      // Load executions immediately
      const loadExecutions = async () => {
        try {
          console.log('📊 Fetching executions for flowId:', flowId)
          const executions = await flowService.getFlowExecutions(workspaceId, flowId)
          console.log('📊 Fetched executions:', executions?.length || 0)
          console.log('Is array?', Array.isArray(executions))
          setFlowExecutions(Array.isArray(executions) ? executions : [])
        } catch (error) {
          console.error('Error loading executions:', error)
          setFlowExecutions([])
        }
      }
      
      loadExecutions()
      
      // Poll every 3 seconds if there are running/pending executions
      const interval = setInterval(async () => {
        try {
          const executions = await flowService.getFlowExecutions(workspaceId, flowId)
          setFlowExecutions(Array.isArray(executions) ? executions : [])
          
          // Stop polling if no running/pending executions
          if (Array.isArray(executions)) {
            const hasActive = executions.some(e => 
              e.status === 'running' || e.status === 'pending'
            )
            if (!hasActive) {
              clearInterval(interval)
            }
          }
        } catch (error) {
          console.error('Error polling executions:', error)
        }
      }, 3000)
      
      return () => clearInterval(interval)
    }
  }, [activeTab, flowId, workspaceId, setFlowExecutions])

  return (
    <div className="fixed inset-0 bg-dark-950 flex flex-col" style={{ paddingTop: '64px' }}>
      {/* Top Navigation Bar with Tabs */}
      <div className="glass border-b border-dark-800 flex flex-col flex-shrink-0">
        {/* Back button and flow info row */}
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => navigate(workspaceId ? wsPath(workspaceId, '/flows') : '/hub/flows')}
              className="p-2 hover:bg-dark-700 rounded-lg transition-colors text-gray-400 hover:text-white"
              title="Back to Flows"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex flex-col">
              <input
                type="text"
                value={flowName}
                onChange={(e) => setFlowName(e.target.value)}
                className="text-lg font-bold gradient-text bg-transparent border-none focus:outline-none focus:ring-1 focus:ring-primary-500 rounded px-2 -ml-2"
                placeholder="Flow Name"
              />
              <input
                type="text"
                value={flowDescription}
                onChange={(e) => setFlowDescription(e.target.value)}
                className="text-xs text-gray-500 bg-transparent border-none focus:outline-none focus:ring-1 focus:ring-primary-500 rounded px-2 -ml-2"
                placeholder="Add description..."
              />
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* Auto-save status indicator - only show when saving or unsaved */}
            {(saveStatus === 'saving' || saveStatus === 'unsaved') && (
              <div className="flex items-center space-x-2 px-3 py-1 rounded text-xs">
                {saveStatus === 'saving' && (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
                    <span className="text-blue-400">Saving...</span>
                  </>
                )}
                {saveStatus === 'unsaved' && (
                  <>
                    <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                    <span className="text-gray-400">Unsaved</span>
                  </>
                )}
              </div>
            )}
            
            {saveMessage && (
              <span className={`text-xs px-3 py-1 rounded ${
                saveMessage.includes('Error') || saveMessage.includes('Failed') 
                  ? 'bg-red-500/20 text-red-400' 
                  : saveMessage.includes('Running') || saveMessage.includes('started')
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'bg-green-500/20 text-green-400'
              }`}>
                {saveMessage}
              </span>
            )}
            
            <button className="px-3 py-1 bg-dark-800 hover:bg-dark-700 rounded text-gray-300 flex items-center space-x-1 text-xs">
              <Download className="w-3 h-3" />
              <span>Export</span>
            </button>

            {flowId && (
              <button
                onClick={() => setShowScheduleModal(true)}
                className="px-3 py-1 bg-dark-800 hover:bg-dark-700 rounded text-gray-300 flex items-center space-x-1 text-xs"
              >
                <Clock className="w-3 h-3" />
                <span>Schedule</span>
              </button>
            )}
            
            <button
              onClick={handleExecuteFlow}
              disabled={isExecuting || !flowId || flowNodes.filter(n => n.type === 'source' && n.config).length === 0 || flowNodes.filter(n => n.type === 'check').length === 0}
              className="btn-primary flex items-center space-x-1 text-xs px-3 py-1 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isExecuting ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>Executing...</span>
                </>
              ) : (
                <>
                  <Play className="w-3 h-3" />
                  <span>Execute</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Tab Menu */}
        <div className="px-4 flex items-center space-x-1 border-t border-dark-800">
          <button
            onClick={() => setActiveTab('flow')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
              activeTab === 'flow'
                ? 'text-primary-400 border-primary-500'
                : 'text-gray-400 border-transparent hover:text-gray-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              <GitBranch className="w-4 h-4" />
              <span>Flow</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('datasources')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
              activeTab === 'datasources'
                ? 'text-primary-400 border-primary-500'
                : 'text-gray-400 border-transparent hover:text-gray-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Database className="w-4 h-4" />
              <span>Datasets</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('runs')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
              activeTab === 'runs'
                ? 'text-primary-400 border-primary-500'
                : 'text-gray-400 border-transparent hover:text-gray-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              <History className="w-4 h-4" />
              <span>Runs</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('reports')}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
              activeTab === 'reports'
                ? 'text-primary-400 border-primary-500'
                : 'text-gray-400 border-transparent hover:text-gray-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              <FileBarChart className="w-4 h-4" />
              <span>Reports</span>
            </div>
          </button>
        </div>
      </div>

      {/* Tab Content - Flow */}
      {activeTab === 'flow' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* AI Prompting Area */}
          <AIFlowPrompt
            onSubmit={handleAiPromptSubmit}
            isProcessing={isProcessingPrompt}
            message={promptMessage}
            onSelectDataSource={handleSelectSuggestedDataSource}
          />

          {/* Main Content Area */}
          <div className="flex-1 flex overflow-hidden relative">
            {/* Component Library Sidebar */}
            <ComponentLibrary
              checks={filteredChecks}
              selectedCategory={selectedCategory}
              categories={categories}
              onCategorySelect={setSelectedCategory}
              onCheckAdd={handleAddComponent}
              isVisible={showLibrary}
              onToggle={setShowLibrary}
            />

            {/* Flow Canvas */}
            <FlowCanvas
              nodes={flowNodes}
              selectedNode={selectedNode}
              draggedNode={draggedNode}
              connectionStart={connectionStart}
              mousePos={mousePos}
              checks={allChecks}
              onNodeMouseDown={handleNodeMouseDown}
              onCanvasMouseMove={handleCanvasMouseMove}
              onCanvasMouseUp={handleCanvasMouseUp}
              onStartConnection={handleStartConnection}
              onEndConnection={handleEndConnection}
              onDeleteNode={handleDeleteNode}
              onDuplicateNode={handleDuplicateNode}
              onNodeClick={handleNodeClick}
            />

            {/* Check Configuration Panel */}
            {showCheckConfig && selectedNode && selectedNode.type === 'check' && (
              <CheckConfigPanel
                node={selectedNode}
                checkConfig={checkConfig}
                onConfigChange={setCheckConfig}
                onClose={() => setShowCheckConfig(false)}
                onSave={handleSaveCheckConfig}
                allNodes={flowNodes}
                availableDatasets={availableDatasets}
                loadingDatasets={loadingDatasets}
              />
            )}

            {/* Dataset Configuration Panel */}
            {showSourceConfig && selectedNode && selectedNode.type === 'source' && (
              <DatasetConfigPanel
                node={selectedNode}
                onClose={() => setShowSourceConfig(false)}
                onSave={handleSaveSourceConfig}
              />
            )}
          </div>
        </div>
      )}

      {/* Tab Content - Data Sources (New Data Assets Panel) */}
      {activeTab === 'datasources' && (
        <DataAssetsPanel 
          onAddToFlow={(asset) => {
            console.log('Adding asset to flow:', asset)
            
            // Build config based on asset type
            let config: any = {}
            
            if (asset.type === 'table' && asset.metadata) {
              // Database table asset
              // Extract just the table name from "schema.table" format
              const tableNameParts = asset.metadata.table_name?.split('.') || []
              const tableName = tableNameParts.length > 1 ? tableNameParts[1] : (tableNameParts[0] || asset.name)
              
              config = {
                id: asset.metadata.datasource_id,  // Required by FlowCanvas to recognize as configured
                name: asset.name,  // Required by FlowCanvas to recognize as configured
                data_source_id: asset.metadata.datasource_id,  // Required by flow execution validator
                datasource_id: asset.metadata.datasource_id,
                datasource_name: asset.metadata.datasource_name || asset.name,
                database_name: asset.metadata.database_name,
                schema_name: asset.metadata.schema_name,
                table_name: tableName,  // Just the table name, schema_name is separate
                connection_type: asset.metadata.connection_type || asset.source,
                host: asset.metadata.host,
                type: asset.source,
                metadata: {
                  rowCount: asset.metadata.rows || asset.rows,
                  database: asset.metadata.database,
                  columns: asset.metadata.columns || []
                }
              }
            } else {
              // File asset (CSV, Excel, Parquet, JSON)
              config = {
                id: asset.id,  // Required by FlowCanvas to recognize as configured
                name: asset.name,  // Required by FlowCanvas to recognize as configured
                file_id: asset.id,
                file_name: asset.name,
                file_type: asset.type,
                file_path: asset.metadata?.file_path,
                source: asset.source,
                type: asset.type,
                metadata: {
                  rowCount: asset.metadata?.rows || asset.rows,
                  fileSize: asset.metadata?.file_size,
                  // Include actual column metadata from the asset
                  columns: asset.metadata?.columns || []
                }
              }
              
              // Add columns array for backwards compatibility
              if (asset.metadata?.columns && Array.isArray(asset.metadata.columns)) {
                config.columns = asset.metadata.columns.map((col: any) => {
                  if (typeof col === 'object' && col.column_name) {
                    return {
                      name: col.column_name,
                      column_name: col.column_name,
                      data_type: col.data_type,
                      is_nullable: col.is_nullable
                    }
                  }
                  return col
                })
              } else {
                config.columns = []
              }
            }
            
            // Create a new data source node with the selected asset
            const newNode = {
              id: `node-${Date.now()}`,
              type: 'source' as const,
              category: 'source',
              name: asset.name,
              x: 100 + (flowNodes.length * 20),  // Offset each new node slightly
              y: 100 + (flowNodes.length * 20),
              connections: [],
              config: config
            }
            
            setFlowNodes([...flowNodes, newNode])
            // Switch back to flow tab
            setActiveTab('flow')
          }}
        />
      )}

      {/* Tab Content - Runs */}
      {activeTab === 'runs' && flowId && (
        <FlowExecutionPanel
          flowId={flowId}
          executions={flowExecutions || []}
          currentExecution={currentExecution}
          onRefresh={async () => {
            if (workspaceId && flowId) {
              const executions = await flowService.getFlowExecutions(workspaceId, flowId)
              setFlowExecutions(executions)
            }
          }}
          onViewReport={(execution) => {
            console.log('📊 View Report clicked for execution:', execution.id)
            setSelectedExecutionForReport(execution)
            setActiveTab('reports')
          }}
        />
      )}

      {activeTab === 'runs' && !flowId && (
        <div className="flex-1 flex items-center justify-center">
          <div className="glass p-12 text-center rounded-lg">
            <History className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-300 mb-2">No Flow Selected</h3>
            <p className="text-gray-500">Save your flow first to view execution history</p>
          </div>
        </div>
      )}

      {/* Tab Content - Reports */}
      {activeTab === 'reports' && flowId && flowExecutions.length > 0 && !selectedExecutionForReport && (
        <div className="flex-1 overflow-auto p-6">
          <div className="max-w-7xl mx-auto space-y-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-white">Flow Execution Reports</h2>
              <div className="text-sm text-gray-400">
                {flowExecutions.length} execution{flowExecutions.length !== 1 ? 's' : ''} found
              </div>
            </div>

            {/* Show last execution summary */}
            {flowExecutions.length > 0 && (
              <div className="glass rounded-lg p-6">
                <h3 className="text-lg font-semibold text-white mb-4">Latest Execution Summary</h3>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="glass-light rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Status</div>
                    <div className="text-xl font-bold text-white capitalize">{flowExecutions[0].status}</div>
                  </div>
                  <div className="glass-light rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Nodes Executed</div>
                    <div className="text-xl font-bold text-white">{flowExecutions[0].nodes_executed || 0}</div>
                  </div>
                  <div className="glass-light rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Passed</div>
                    <div className="text-xl font-bold text-green-400">{flowExecutions[0].nodes_passed || 0}</div>
                  </div>
                  <div className="glass-light rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Failed</div>
                    <div className="text-xl font-bold text-red-400">{flowExecutions[0].nodes_failed || 0}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Execution History Table */}
            <div className="glass rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Execution History</h3>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-dark-700">
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Execution ID</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Started</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Duration</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Status</th>
                      <th className="text-right py-3 px-4 text-sm font-medium text-gray-400">Nodes</th>
                      <th className="text-right py-3 px-4 text-sm font-medium text-gray-400">Passed</th>
                      <th className="text-right py-3 px-4 text-sm font-medium text-gray-400">Failed</th>
                      <th className="text-right py-3 px-4 text-sm font-medium text-gray-400">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flowExecutions.map((execution) => (
                      <tr key={execution.id} className="border-b border-dark-800 hover:bg-dark-800/50">
                        <td className="py-3 px-4 text-sm text-gray-300 font-mono">
                          {execution.id.slice(0, 8)}...
                        </td>
                        <td className="py-3 px-4 text-sm text-gray-300">
                          {new Date(execution.started_at).toLocaleString()}
                        </td>
                        <td className="py-3 px-4 text-sm text-gray-300">
                          {execution.duration_seconds ? `${execution.duration_seconds}s` : 'N/A'}
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${
                            execution.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                            execution.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                            execution.status === 'running' ? 'bg-blue-500/20 text-blue-400' :
                            'bg-gray-500/20 text-gray-400'
                          }`}>
                            {execution.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-sm text-gray-300 text-right">
                          {execution.nodes_executed || 0}
                        </td>
                        <td className="py-3 px-4 text-sm text-green-400 text-right">
                          {execution.nodes_passed || 0}
                        </td>
                        <td className="py-3 px-4 text-sm text-red-400 text-right">
                          {execution.nodes_failed || 0}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => setSelectedExecutionForReport(execution)}
                            className="px-3 py-1 bg-primary-600 hover:bg-primary-700 text-white text-xs rounded transition-colors"
                          >
                            View DQ Report
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Detailed Execution Report View */}
      {activeTab === 'reports' && selectedExecutionForReport && (
        <div className="flex-1 overflow-auto">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 border-b border-gray-700 px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-white mb-1">Data Quality Execution Report</h1>
                <p className="text-sm text-gray-400">
                  Detailed analysis of flow execution results
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedExecutionForReport(null)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg font-medium flex items-center gap-2 transition-colors"
                >
                  <ArrowLeft className="w-5 h-5" />
                  Back to History
                </button>
                <button
                  onClick={async () => {
                    try {
                      await generateExecutionReportPDF(
                        selectedExecutionForReport,
                        reportNodeResults,
                        flowName || 'Unnamed Flow'
                      );
                    } catch (error) {
                      console.error('Error generating PDF:', error);
                      toast.error('Failed to generate PDF. Please try again.');
                    }
                  }}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium flex items-center gap-2 transition-colors"
                >
                  <Download className="w-5 h-5" />
                  Export PDF
                </button>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="p-6 space-y-6">
            {/* Flow Run Header */}
            <section className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border border-blue-700 rounded-lg p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h1 className="text-2xl font-bold text-white mb-2">{flowName || 'Flow Execution'}</h1>
                  <div className="flex items-center gap-4 text-sm text-gray-300">
                    <span className="flex items-center gap-1">
                      <Play className="w-4 h-4" />
                      Run ID: {selectedExecutionForReport.id.slice(0, 16)}
                    </span>
                    <span>Trigger: {selectedExecutionForReport.trigger || 'Manual'}</span>
                    <span>Actor: {selectedExecutionForReport.executed_by_name || 'system'}</span>
                  </div>
                </div>
                <div
                  className={`px-4 py-2 rounded-full text-sm font-medium ${
                    selectedExecutionForReport.status === 'completed'
                      ? 'bg-green-500/20 text-green-400'
                      : selectedExecutionForReport.status === 'failed'
                      ? 'bg-red-500/20 text-red-400'
                      : 'bg-yellow-500/20 text-yellow-400'
                  }`}
                >
                  {selectedExecutionForReport.status === 'completed' ? 'Success' : selectedExecutionForReport.status === 'failed' ? 'Failed' : 'Partial Success'}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-400">Start Time</p>
                  <p className="text-lg font-semibold text-white">
                    {new Date(selectedExecutionForReport.started_at).toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-400">Duration</p>
                  <p className="text-lg font-semibold text-white">
                    {(() => {
                      if (selectedExecutionForReport.duration_seconds) {
                        return `${Math.floor(selectedExecutionForReport.duration_seconds / 60)}m ${selectedExecutionForReport.duration_seconds % 60}s`
                      }
                      if (selectedExecutionForReport.result_summary?.execution_time) {
                        const seconds = Math.floor(selectedExecutionForReport.result_summary.execution_time)
                        return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
                      }
                      if (selectedExecutionForReport.started_at && selectedExecutionForReport.completed_at) {
                        const duration = Math.floor((new Date(selectedExecutionForReport.completed_at).getTime() - 
                                        new Date(selectedExecutionForReport.started_at).getTime()) / 1000)
                        return `${Math.floor(duration / 60)}m ${duration % 60}s`
                      }
                      if (selectedExecutionForReport.created_at && selectedExecutionForReport.updated_at) {
                        const duration = Math.floor((new Date(selectedExecutionForReport.updated_at).getTime() - 
                                        new Date(selectedExecutionForReport.created_at).getTime()) / 1000)
                        return `${Math.floor(duration / 60)}m ${duration % 60}s`
                      }
                      return 'N/A'
                    })()}
                  </p>
                </div>
              </div>
            </section>

            {/* Datasets Involved - Placeholder */}
            <section>
              <h2 className="text-xl font-bold text-white mb-4">📦 Datasets Involved</h2>
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg overflow-hidden">
                <table className="w-full">
                  <thead className="bg-gray-800">
                    <tr>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">DATASET</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">SOURCE</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">ROWS ANALYZED</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">STATUS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadingReportData ? (
                      <tr className="border-t border-gray-700">
                        <td colSpan={4} className="py-6 px-4 text-center text-sm text-gray-400">
                          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                          Loading dataset information...
                        </td>
                      </tr>
                    ) : reportNodeResults.filter(node => node.node_type === 'source').length > 0 ? (
                      reportNodeResults
                        .filter(node => node.node_type === 'source')
                        .map((sourceNode, idx) => (
                          <tr key={idx} className="border-t border-gray-700">
                            <td className="py-3 px-4 text-sm text-white">
                              {sourceNode.result_data?.file_name ||
                               sourceNode.result_data?.source_name ||
                               sourceNode.result_data?.table_name ||
                               sourceNode.result_data?.dataset ||
                               'Unknown'}
                            </td>
                            <td className="py-3 px-4 text-sm text-gray-300">
                              {(() => {
                                const srcType = sourceNode.result_data?.source_type;
                                if (srcType === 'file') {
                                  const ft = (sourceNode.result_data?.file_type || 'file').toUpperCase();
                                  return `${ft} File`;
                                }
                                const connType = sourceNode.result_data?.data_source?.type || 'PostgreSQL';
                                const schemaName = sourceNode.result_data?.schema_name || 'Production';
                                return `${connType} - ${schemaName}`;
                              })()}
                            </td>
                            <td className="py-3 px-4 text-sm text-gray-300">
                              {(() => {
                                // Try to get row count from various possible fields
                                const rowCount = sourceNode.result_data?.row_count || 
                                               sourceNode.result_data?.rows_scanned || 
                                               sourceNode.result_data?.total_rows ||
                                               sourceNode.result_data?.output_data?.row_count;
                                
                                // If source doesn't have it, try to get from execution summary or check nodes
                                if (!rowCount || rowCount === 0) {
                                  // Look for a check node that might have the row count
                                  const checkNode = reportNodeResults.find(n => n.node_type === 'check');
                                  if (checkNode?.result_data?.rows_scanned) {
                                    return checkNode.result_data.rows_scanned.toLocaleString();
                                  }
                                  if (selectedExecutionForReport.result_summary?.total_rows_scanned) {
                                    return selectedExecutionForReport.result_summary.total_rows_scanned.toLocaleString();
                                  }
                                }
                                
                                return rowCount ? rowCount.toLocaleString() : '0';
                              })()}
                            </td>
                            <td className="py-3 px-4">
                              <span className={`px-2 py-1 rounded text-xs font-medium ${
                                sourceNode.status === 'completed' 
                                  ? 'bg-green-500/20 text-green-400'
                                  : sourceNode.status === 'failed'
                                  ? 'bg-red-500/20 text-red-400'
                                  : 'bg-yellow-500/20 text-yellow-400'
                              }`}>
                                {sourceNode.status === 'completed' ? 'Success' : sourceNode.status}
                              </span>
                            </td>
                          </tr>
                        ))
                    ) : (
                      <tr className="border-t border-gray-700">
                        <td className="py-3 px-4 text-sm text-white">
                          {flowName || 'Dataset'}
                        </td>
                        <td className="py-3 px-4 text-sm text-gray-300">
                          PostgreSQL - Production
                        </td>
                        <td className="py-3 px-4 text-sm text-gray-300">
                          {(() => {
                            // Try execution summary first
                            if (selectedExecutionForReport.result_summary?.total_rows_scanned) {
                              return selectedExecutionForReport.result_summary.total_rows_scanned.toLocaleString();
                            }
                            // Then try to find from check nodes
                            const checkNode = reportNodeResults.find(n => n.node_type === 'check');
                            if (checkNode?.result_data?.rows_scanned) {
                              return checkNode.result_data.rows_scanned.toLocaleString();
                            }
                            return '0';
                          })()}
                        </td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-1 rounded text-xs font-medium bg-green-500/20 text-green-400">
                            Success
                          </span>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Run-Level Metrics */}
            <section>
              <h2 className="text-xl font-bold text-white mb-4">📊 Run-Level Metrics</h2>
              {(() => {
                // Count only check nodes (source nodes are not "checks")
                const checkNodes = reportNodeResults.filter(n => n.node_type === 'check');
                const totalChecks = checkNodes.length;
                const passedChecks = checkNodes.filter(n => n.status === 'completed').length;
                const failedChecks = checkNodes.filter(n => n.status === 'failed').length;
                const skippedChecks = checkNodes.filter(n => n.status === 'skipped').length;
                const passRate = totalChecks > 0 ? Math.round((passedChecks / totalChecks) * 100) : 0;
                return (
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                      <p className="text-sm text-gray-400 mb-2">Total Checks</p>
                      <p className="text-3xl font-bold text-white">{totalChecks}</p>
                    </div>
                    <div className="bg-green-900/20 border border-green-700 rounded-lg p-4">
                      <p className="text-sm text-gray-400 mb-2 flex items-center gap-1">
                        <CheckCircle className="w-4 h-4" /> Passed
                      </p>
                      <p className="text-3xl font-bold text-green-400">{passedChecks}</p>
                    </div>
                    <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-4">
                      <p className="text-sm text-gray-400 mb-2 flex items-center gap-1">
                        ⚠️ Warnings
                      </p>
                      <p className="text-3xl font-bold text-yellow-400">0</p>
                    </div>
                    <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
                      <p className="text-sm text-gray-400 mb-2 flex items-center gap-1">
                        ⛔ Failed
                      </p>
                      <p className="text-3xl font-bold text-red-400">{failedChecks}</p>
                    </div>
                    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                      <p className="text-sm text-gray-400 mb-2">Skipped</p>
                      <p className="text-3xl font-bold text-gray-400">{skippedChecks}</p>
                    </div>
                    <div className="bg-yellow-900/20 border border-yellow-700 rounded-lg p-4">
                      <p className="text-sm text-gray-400 mb-2">Pass Rate</p>
                      <p className="text-3xl font-bold text-white">{passRate}%</p>
                    </div>
                  </div>
                );
              })()}
            </section>

            {/* Checks Applied - Placeholder */}
            <section>
              <h2 className="text-xl font-bold text-white mb-4">🔧 Checks Applied</h2>
              <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-6">
                <div className="mb-4">
                  <input
                    type="text"
                    placeholder="Search checks..."
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                  />
                </div>
                {loadingReportData ? (
                  <div className="text-sm text-gray-400 text-center py-8">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                    Loading check results...
                  </div>
                ) : reportNodeResults.filter(node => node.node_type === 'check').length > 0 ? (
                  <div className="space-y-3">
                    {reportNodeResults
                      .filter(node => node.node_type === 'check')
                      .map((checkNode, idx) => {
                        const rd = checkNode.result_data || {}
                        const checkStatus = rd.check_status as string | undefined
                        const statusBadge = checkStatus === 'PASS'
                          ? { text: 'PASS', cls: 'bg-green-500/20 text-green-400' }
                          : checkStatus === 'WARN'
                            ? { text: 'WARN', cls: 'bg-yellow-500/20 text-yellow-400' }
                            : checkStatus === 'FAIL'
                              ? { text: 'FAIL', cls: 'bg-red-500/20 text-red-400' }
                              : checkNode.status === 'completed'
                                ? { text: 'PASSED', cls: 'bg-green-500/20 text-green-400' }
                                : checkNode.status === 'failed'
                                  ? { text: 'FAILED', cls: 'bg-red-500/20 text-red-400' }
                                  : { text: checkNode.status.toUpperCase(), cls: 'bg-yellow-500/20 text-yellow-400' }
                        const checkName = rd.node_label || (rd.check_type ? rd.check_type.charAt(0).toUpperCase() + rd.check_type.slice(1) : 'Data Quality Check')
                        return (
                        <div key={idx} className="bg-gray-700/50 border border-gray-600 rounded-lg p-4">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-3">
                              <span className="text-lg">{rd.check_type === 'completeness' ? '📊' : '✓'}</span>
                              <div>
                                <h3 className="text-white font-medium">{checkName}</h3>
                                <div className="flex items-center gap-2 mt-0.5">
                                  {rd.check_type && (
                                    <span className="text-xs px-1.5 py-0.5 bg-primary-500/20 text-primary-400 rounded">{rd.check_type}</span>
                                  )}
                                  <p className="text-sm text-gray-400">
                                    {rd.columns?.length 
                                      ? `Columns: ${rd.columns.join(', ')}`
                                      : checkNode.status === 'failed' && !rd.pass_rate
                                        ? 'Check failed'
                                        : 'No columns specified'}
                                  </p>
                                </div>
                              </div>
                            </div>
                            <span className={`px-3 py-1 rounded text-sm font-medium ${statusBadge.cls}`}>
                              {statusBadge.text}
                            </span>
                          </div>
                          <div className="grid grid-cols-3 gap-4 text-sm">
                            <div>
                              <div className="text-gray-400">Rows Checked</div>
                              <div className="text-white font-medium">
                                {checkNode.result_data?.rows_scanned?.toLocaleString() || 
                                 checkNode.result_data?.total_rows?.toLocaleString() || 
                                 checkNode.result_data?.rows_checked?.toLocaleString() || '0'}
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-400">Valid Rows</div>
                              <div className="text-green-400 font-medium">
                                {checkNode.result_data?.rows_passed?.toLocaleString() || 
                                 checkNode.result_data?.valid_rows?.toLocaleString() || 
                                 checkNode.result_data?.passed_rows?.toLocaleString() || '0'}
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-400">Invalid Rows</div>
                              <div className="text-red-400 font-medium">
                                {checkNode.result_data?.rows_failed?.toLocaleString() || 
                                 checkNode.result_data?.invalid_rows?.toLocaleString() || 
                                 checkNode.result_data?.failed_rows?.toLocaleString() || '0'}
                              </div>
                            </div>
                          </div>
                          {/* Error message for failed checks with no result data */}
                          {checkNode.status === 'failed' && checkNode.error_message && !rd.pass_rate && (
                            <div className="mt-2 px-3 py-2 bg-red-900/20 border border-red-700/40 rounded text-xs text-red-400">
                              {checkNode.error_message}
                            </div>
                          )}
                          {(rd.pass_rate !== undefined || rd.completeness_percentage !== undefined) && (
                            <div className="mt-3">
                              {/* Threshold info */}
                              {rd.threshold_pass !== undefined && (
                                <div className="flex items-center gap-2 text-xs mb-1">
                                  <span className="text-gray-500">Score:</span>
                                  <span className={checkStatus === 'PASS' ? 'text-green-400 font-medium' : checkStatus === 'WARN' ? 'text-yellow-400 font-medium' : 'text-red-400 font-medium'}>
                                    {typeof rd.pass_rate === 'number' ? rd.pass_rate.toFixed(2) : rd.pass_rate}%
                                  </span>
                                  <span className="text-gray-600">|</span>
                                  <span className="text-gray-500">Pass ≥ {rd.threshold_pass}%</span>
                                  {rd.threshold_warn != null && (
                                    <><span className="text-gray-600">|</span><span className="text-gray-500">Warn ≥ {rd.threshold_warn}%</span></>
                                  )}
                                </div>
                              )}
                              <div className="flex items-center justify-between text-sm mb-1">
                                <span className="text-gray-400">
                                  {rd.check_type === 'completeness' ? 'Completeness' : 'Pass Rate'}
                                </span>
                                <span className="text-white font-medium">
                                  {(rd.pass_rate || rd.completeness_percentage || 0).toFixed(2)}%
                                </span>
                              </div>
                              <div className="w-full bg-gray-600 rounded-full h-2">
                                <div 
                                  className={`h-2 rounded-full transition-all ${
                                    checkStatus === 'PASS' ? 'bg-green-500' :
                                    checkStatus === 'WARN' ? 'bg-yellow-500' :
                                    checkStatus === 'FAIL' ? 'bg-red-500' : 'bg-green-500'
                                  }`}
                                  style={{ width: `${rd.pass_rate || rd.completeness_percentage || 0}%` }}
                                />
                              </div>
                              {/* Group breakdown */}
                              {rd.check_mode === 'group' && Array.isArray(rd.group_results) && rd.group_results.length > 0 && (
                                <div className="mt-2 text-xs space-y-0.5">
                                  <div className="flex flex-wrap gap-x-3">
                                    {rd.group_results.map((grp: any, gi: number) => {
                                      const label = Object.values(grp.group_key || {}).join(', ') || `Group ${gi + 1}`
                                      const rate = typeof grp.pass_rate === 'number' ? grp.pass_rate.toFixed(1) : grp.pass_rate
                                      const cls = grp.check_status === 'PASS' ? 'text-green-400' : grp.check_status === 'WARN' ? 'text-yellow-400' : 'text-red-400'
                                      return <span key={gi} className={cls}>{label}: {grp.passed_rows}/{grp.total_rows} ({rate}%)</span>
                                    })}
                                  </div>
                                  {(() => {
                                    const failing = rd.group_results.filter((g: any) => g.check_status !== 'PASS')
                                    if (!failing.length) return null
                                    const names = failing.map((g: any) => Object.values(g.group_key || {}).join(', ')).join(', ')
                                    return <div className="text-red-400">At {rd.threshold_pass}%, {names} {failing.length === 1 ? 'fails' : 'fail'}</div>
                                  })()}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                        )
                      })}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400 text-center py-8">
                    No check nodes found in this execution.
                    <br />
                    <span className="text-xs text-gray-600">Navigate to the Runs tab to see node-level execution details.</span>
                  </p>
                )}
              </div>
            </section>

            {/* Error Details */}
            {selectedExecutionForReport.error_message && (
              <section>
                <h2 className="text-xl font-bold text-red-400 mb-4">❌ Error Details</h2>
                <div className="bg-red-900/20 border border-red-700 rounded-lg p-6">
                  <p className="text-red-300 mb-2">{selectedExecutionForReport.error_message}</p>
                  {selectedExecutionForReport.error_details && (
                    <pre className="mt-2 text-xs text-gray-400 overflow-auto p-4 bg-gray-900/50 rounded">
                      {JSON.stringify(selectedExecutionForReport.error_details, null, 2)}
                    </pre>
                  )}
                </div>
              </section>
            )}
          </div>
        </div>
      )}

      {activeTab === 'reports' && flowId && flowExecutions.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <div className="glass p-12 text-center rounded-lg">
            <FileBarChart className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-300 mb-2">No Reports Available</h3>
            <p className="text-gray-500">Execute the flow to generate reports</p>
          </div>
        </div>
      )}

      {activeTab === 'reports' && !flowId && (
        <div className="flex-1 flex items-center justify-center">
          <div className="glass p-12 text-center rounded-lg">
            <FileBarChart className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-gray-300 mb-2">Reports Tab</h3>
            <p className="text-gray-500">Save the flow first to view reports</p>
          </div>
        </div>
      )}

      {/* F115 — Schedule Modal */}
      {showScheduleModal && flowId && workspaceId && (
        <FlowScheduleModal
          workspaceId={workspaceId}
          flowId={flowId}
          onClose={() => setShowScheduleModal(false)}
        />
      )}
    </div>
  )
}
