import { useState } from 'react'
import { Sparkles, Send, Loader2, X, CheckCircle, XCircle, AlertTriangle, Info, Database } from 'lucide-react'
import { PromptMessage } from './types'

interface AIFlowPromptProps {
  onSubmit: (prompt: string) => Promise<void>
  isProcessing: boolean
  message: PromptMessage | null
  onSelectDataSource?: (dataSource: any) => void
}

export function AIFlowPrompt({ onSubmit, isProcessing, message, onSelectDataSource }: AIFlowPromptProps) {
  const [prompt, setPrompt] = useState<string>('')
  const [showPrompt, setShowPrompt] = useState(true)

  const handleSubmit = async () => {
    if (!prompt.trim() || isProcessing) return
    await onSubmit(prompt)
    if (message?.type === 'success') {
      setTimeout(() => setPrompt(''), 3000)
    }
  }

  const handleSelectSuggestion = (dataSource: any) => {
    if (onSelectDataSource) {
      onSelectDataSource(dataSource)
      setPrompt('')
    }
  }

  if (!showPrompt) {
    return (
      <div className="glass border-b border-dark-800 px-4 py-2 flex-shrink-0">
        <button
          onClick={() => setShowPrompt(true)}
          className="text-xs text-gray-400 hover:text-primary-400 flex items-center space-x-2"
        >
          <Sparkles className="w-3 h-3" />
          <span>Show AI Flow Builder</span>
        </button>
      </div>
    )
  }

  return (
    <div className="glass border-b border-dark-800 px-4 py-3 flex-shrink-0">
      <div className="flex items-start space-x-3">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-2">
            <Sparkles className="w-4 h-4 text-primary-400" />
            <span className="text-sm font-medium text-gray-200">AI Flow Builder</span>
            <button
              onClick={() => setShowPrompt(false)}
              className="ml-auto p-1 hover:bg-dark-800 rounded text-gray-500 hover:text-gray-300"
              title="Hide AI prompting"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
          <div className="flex items-center space-x-2">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSubmit()
                }
              }}
              placeholder="e.g., Apply completeness check on email and age columns with 90% threshold, check for Null"
              className="flex-1 bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={isProcessing}
            />
            <button
              onClick={handleSubmit}
              disabled={isProcessing || !prompt.trim()}
              className="btn-primary px-4 py-2 text-sm flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Processing...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Build</span>
                </>
              )}
            </button>
          </div>
          {message && (
            <div className={`mt-2 px-3 py-2 rounded-lg text-xs ${
              message.type === 'success' ? 'bg-green-500/20 text-green-400' :
              message.type === 'error' ? 'bg-red-500/20 text-red-400' :
              message.type === 'question' ? 'bg-yellow-500/20 text-yellow-400' :
              message.type === 'suggestions' ? 'bg-blue-500/10 border border-blue-500/30 text-blue-300' :
              'bg-blue-500/20 text-blue-400'
            }`}>
              <div className="flex items-start space-x-2 mb-2">
                {message.type === 'success' && <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                {message.type === 'error' && <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                {message.type === 'question' && <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                {message.type === 'suggestions' && <Database className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                {message.type === 'info' && <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                <span className="whitespace-pre-wrap">{message.text}</span>
              </div>
              
              {/* Show suggested data sources */}
              {message.type === 'suggestions' && message.suggestions && message.suggestions.length > 0 && (
                <div className="mt-3 space-y-2">
                  <p className="text-xs font-medium text-blue-400 mb-2">Select a data source:</p>
                  {message.suggestions.map((ds: any, idx: number) => {
                    // Build full table path
                    const fullPath = ds.schema_name && ds.table_name 
                      ? `${ds.schema_name}.${ds.table_name}`
                      : ds.table_name || ds.name || 'Unknown'
                    
                    return (
                      <button
                        key={idx}
                        onClick={() => handleSelectSuggestion(ds)}
                        className="w-full text-left p-3 bg-dark-800 hover:bg-dark-700 border border-dark-700 hover:border-primary-500/50 rounded-lg transition-all group"
                      >
                        <div className="flex items-start space-x-3">
                          <Database className="w-4 h-4 text-primary-400 mt-0.5 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center space-x-2">
                              <p className="font-medium text-white text-sm">{fullPath}</p>
                              {ds.match_score && ds.match_score > 10 && (
                                <span className="text-xs px-2 py-0.5 bg-primary-500/20 text-primary-300 rounded">
                                  {ds.match_score}% match
                                </span>
                              )}
                            </div>
                            {ds.metadata?.columns && ds.metadata.columns.length > 0 && (
                              <p className="text-xs text-gray-600 mt-1 truncate">
                                {ds.metadata.columns.length} columns: {
                                  Array.isArray(ds.metadata.columns) 
                                    ? ds.metadata.columns.slice(0, 6).map((col: any) => 
                                        typeof col === 'string' ? col : col.column_name || col.name
                                      ).filter(Boolean).join(', ')
                                    : ''
                                }
                                {Array.isArray(ds.metadata.columns) && ds.metadata.columns.length > 6 && '...'}
                              </p>
                            )}
                            {ds.match_reason && ds.match_reason !== 'Available data source' && (
                              <p className="text-xs text-blue-400/80 mt-1 italic">✓ {ds.match_reason}</p>
                            )}
                            {ds.metadata?.rowCount && (
                              <p className="text-xs text-gray-700 mt-1">
                                {ds.metadata.rowCount.toLocaleString()} rows
                              </p>
                            )}
                          </div>
                          <CheckCircle className="w-4 h-4 text-gray-600 group-hover:text-primary-400 flex-shrink-0" />
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
