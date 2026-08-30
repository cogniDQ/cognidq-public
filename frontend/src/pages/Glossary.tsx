import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Plus, Upload, Download, Trash2, Search, Tag, CheckCircle, Edit, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useTenantId } from '@/hooks/useTenantId'
import {
  listTenantGlossaryTerms,
  createTenantGlossaryTerm,
  updateTenantGlossaryTerm,
  deleteTenantGlossaryTerm,
  importTenantGlossaryCSV,
  exportTenantGlossaryCSV,
} from '@/services/glossaryService'
import type { GlossaryTerm, GlossaryTermCreate } from '@/services/glossaryService'

export default function Glossary() {
  const tenantId = useTenantId()
  const queryClient = useQueryClient()

  const [searchTerm, setSearchTerm] = useState('')
  const [selectedDomain, setSelectedDomain] = useState<string>('all')
  const [showAddModal, setShowAddModal] = useState(false)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [editingTerm, setEditingTerm] = useState<GlossaryTerm | null>(null)
  const [newTerm, setNewTerm] = useState<Partial<GlossaryTermCreate>>({
    business_name: '',
    technical_name: '',
    data_type: 'string',
    definition: '',
    is_mandatory: false,
    owner: '',
    domain: '',
    synonyms: [],
    allowed_values: null,
  })

  const { data: glossaryData, isLoading } = useQuery({
    queryKey: ['glossary', tenantId, searchTerm, selectedDomain === 'all' ? undefined : selectedDomain],
    queryFn: () =>
      listTenantGlossaryTerms(tenantId, {
        search: searchTerm || undefined,
        domain: selectedDomain === 'all' ? undefined : selectedDomain,
        page_size: 200,
      }),
    enabled: !!tenantId,
    staleTime: 30_000,
  })

  const glossary = glossaryData?.items ?? []
  const total = glossaryData?.total ?? 0
  const domains = ['all', ...new Set(glossary.map(t => t.domain).filter(Boolean) as string[])]

  const createMutation = useMutation({
    mutationFn: (payload: GlossaryTermCreate) => createTenantGlossaryTerm(tenantId, payload),
    onSuccess: () => {
      toast.success('Term created')
      queryClient.invalidateQueries({ queryKey: ['glossary', tenantId] })
      setShowAddModal(false)
      resetNewTerm()
    },
    onError: () => toast.error('Failed to create term'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ termId, payload }: { termId: string; payload: Partial<GlossaryTermCreate> }) =>
      updateTenantGlossaryTerm(tenantId, termId, payload),
    onSuccess: () => {
      toast.success('Term updated')
      queryClient.invalidateQueries({ queryKey: ['glossary', tenantId] })
      setEditingTerm(null)
      setShowAddModal(false)
      resetNewTerm()
    },
    onError: () => toast.error('Failed to update term'),
  })

  const deleteMutation = useMutation({
    mutationFn: (termId: string) => deleteTenantGlossaryTerm(tenantId, termId),
    onSuccess: () => {
      toast.success('Term deleted')
      queryClient.invalidateQueries({ queryKey: ['glossary', tenantId] })
    },
    onError: () => toast.error('Failed to delete term'),
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => importTenantGlossaryCSV(tenantId, file),
    onSuccess: (result) => {
      toast.success(`Imported ${result.imported} terms${result.skipped ? `, ${result.skipped} skipped` : ''}`)
      queryClient.invalidateQueries({ queryKey: ['glossary', tenantId] })
      setShowUploadModal(false)
    },
    onError: () => toast.error('Failed to import CSV'),
  })

  const resetNewTerm = useCallback(() => {
    setNewTerm({
      business_name: '', technical_name: '', data_type: 'string',
      definition: '', is_mandatory: false, owner: '', domain: '',
      synonyms: [], allowed_values: null,
    })
  }, [])

  const handleAddTerm = useCallback(() => {
    if (!newTerm.business_name) return
    if (editingTerm) {
      updateMutation.mutate({ termId: editingTerm.term_id, payload: newTerm })
    } else {
      createMutation.mutate(newTerm as GlossaryTermCreate)
    }
  }, [newTerm, editingTerm, createMutation, updateMutation])

  const handleEdit = useCallback((term: GlossaryTerm) => {
    setEditingTerm(term)
    setNewTerm({
      business_name: term.business_name,
      technical_name: term.technical_name || '',
      data_type: term.data_type || 'string',
      definition: term.definition || '',
      is_mandatory: term.is_mandatory,
      owner: term.owner || '',
      domain: term.domain || '',
      synonyms: term.synonyms || [],
      allowed_values: term.allowed_values,
    })
    setShowAddModal(true)
  }, [])

  const handleDelete = useCallback((term: GlossaryTerm) => {
    if (confirm(`Delete "${term.business_name}"?`)) {
      deleteMutation.mutate(term.term_id)
    }
  }, [deleteMutation])

  const handleExportCSV = useCallback(async () => {
    try {
      const blob = await exportTenantGlossaryCSV(tenantId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `glossary-${new Date().toISOString().split('T')[0]}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Failed to export CSV')
    }
  }, [tenantId])

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold gradient-text">Business Glossary</h1>
          <p className="text-gray-400 mt-2">Map business terms to technical columns for semantic data quality</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setShowUploadModal(true)}
            className="px-4 py-2 bg-dark-800 hover:bg-dark-700 rounded text-gray-300 flex items-center space-x-2"
          >
            <Upload className="w-4 h-4" />
            <span>Import CSV</span>
          </button>
          <button
            onClick={handleExportCSV}
            className="px-4 py-2 bg-dark-800 hover:bg-dark-700 rounded text-gray-300 flex items-center space-x-2"
          >
            <Download className="w-4 h-4" />
            <span>Export CSV</span>
          </button>
          <button
            onClick={() => { setEditingTerm(null); resetNewTerm(); setShowAddModal(true) }}
            className="btn-primary flex items-center space-x-2"
            data-testid="glossary-add-term-btn"
          >
            <Plus className="w-5 h-5" />
            <span>Add Term</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="glass p-6 border border-dark-700">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              placeholder="Search terms, columns, or descriptions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input w-full pl-10"
            />
          </div>

          <div className="flex items-center space-x-3">
            <Tag className="w-5 h-5 text-gray-500" />
            <select
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value)}
              className="input flex-1"
            >
              <option value="all">All Domains</option>
              {domains.filter(d => d !== 'all').map(domain => (
                <option key={domain} value={domain}>{domain}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center space-x-4 mt-4 text-sm text-gray-400">
          <span>Total Terms: <span className="text-primary-400 font-semibold">{total}</span></span>
          <span>Showing: <span className="text-primary-400 font-semibold">{glossary.length}</span></span>
          {isLoading && <Loader2 className="w-4 h-4 animate-spin text-primary-400" />}
        </div>
      </div>

      {/* Glossary Table */}
      <div className="glass border border-dark-700 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-dark-900 border-b border-dark-700">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Business Term
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Technical Column
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Data Type
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Domain
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Mandatory
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Owner
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-800">
              {glossary.map((term) => (
                <tr key={term.term_id} className="hover:bg-dark-900/50 transition-colors">
                  <td className="px-6 py-4">
                    <div>
                      <p className="font-medium text-gray-200">{term.business_name}</p>
                      <p className="text-sm text-gray-500 mt-1">{term.definition}</p>
                      {term.allowed_values && term.allowed_values.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {term.allowed_values.map(val => (
                            <span key={val} className="text-xs px-2 py-0.5 bg-primary-600/20 text-primary-400 rounded">
                              {val}
                            </span>
                          ))}
                        </div>
                      )}
                      {term.synonyms && term.synonyms.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {term.synonyms.map(syn => (
                            <span key={syn} className="text-xs px-2 py-0.5 bg-dark-800 text-gray-500 rounded">
                              {syn}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <code className="text-sm text-primary-400 bg-dark-900 px-2 py-1 rounded">
                      {term.technical_name || '—'}
                    </code>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm text-gray-400">{term.data_type || '—'}</span>
                  </td>
                  <td className="px-6 py-4">
                    {term.domain && (
                      <span className="inline-flex px-2 py-1 text-xs font-medium bg-accent-purple/20 text-accent-purple rounded">
                        {term.domain}
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {term.is_mandatory ? (
                      <CheckCircle className="w-5 h-5 text-green-400" />
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm text-gray-400">{term.owner || '—'}</span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-2">
                      <button onClick={() => handleEdit(term)} className="p-1 hover:bg-dark-800 rounded text-gray-400 hover:text-primary-400">
                        <Edit className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleDelete(term)} className="p-1 hover:bg-dark-800 rounded text-gray-400 hover:text-red-400">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {glossary.length === 0 && (
          <div className="p-12 text-center">
            <BookOpen className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No glossary terms found</p>
            <p className="text-sm text-gray-600 mt-2">
              {searchTerm || selectedDomain !== 'all'
                ? 'Try adjusting your filters'
                : 'Add your first glossary term to get started'}
            </p>
          </div>
        )}
      </div>

      {/* Add Term Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4" data-testid="glossary-term-modal">
          <div className="glass border border-primary-500/30 rounded-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold gradient-text mb-6">{editingTerm ? 'Edit Glossary Term' : 'Add Glossary Term'}</h2>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Business Term *
                  </label>
                  <input
                    type="text"
                    value={newTerm.business_name}
                    onChange={(e) => setNewTerm({ ...newTerm, business_name: e.target.value })}
                    className="input w-full"
                    placeholder="Employee Status"
                    data-testid="glossary-business-name"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Technical Column *
                  </label>
                  <input
                    type="text"
                    value={newTerm.technical_name}
                    onChange={(e) => setNewTerm({ ...newTerm, technical_name: e.target.value })}
                    className="input w-full"
                    placeholder="status"
                    data-testid="glossary-technical-name"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Data Type
                  </label>
                  <select
                    value={newTerm.data_type}
                    onChange={(e) => setNewTerm({ ...newTerm, data_type: e.target.value })}
                    className="input w-full"
                  >
                    <option value="string">String</option>
                    <option value="integer">Integer</option>
                    <option value="decimal">Decimal</option>
                    <option value="boolean">Boolean</option>
                    <option value="date">Date</option>
                    <option value="datetime">DateTime</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Domain
                  </label>
                  <input
                    type="text"
                    value={newTerm.domain}
                    onChange={(e) => setNewTerm({ ...newTerm, domain: e.target.value })}
                    className="input w-full"
                    placeholder="HR, Finance, Customer..."
                    data-testid="glossary-domain"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Description *
                </label>
                <textarea
                  value={newTerm.definition}
                  onChange={(e) => setNewTerm({ ...newTerm, definition: e.target.value })}
                  className="input w-full"
                  rows={3}
                  placeholder="Describe what this term means in business context..."
                  data-testid="glossary-definition"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Allowed Values (comma-separated)
                </label>
                <input
                  type="text"
                  onChange={(e) => setNewTerm({ 
                    ...newTerm, 
                    allowed_values: e.target.value.split(',').map(v => v.trim()).filter(Boolean) 
                  })}
                  className="input w-full"
                  placeholder="ACTIVE, INACTIVE, TERMINATED"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Owner
                </label>
                <input
                  type="text"
                  value={newTerm.owner}
                  onChange={(e) => setNewTerm({ ...newTerm, owner: e.target.value })}
                  className="input w-full"
                  placeholder="HR Department"
                />
              </div>

              <div className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  id="mandatory"
                  checked={newTerm.is_mandatory}
                  onChange={(e) => setNewTerm({ ...newTerm, is_mandatory: e.target.checked })}
                  className="w-4 h-4 bg-dark-800 border-dark-700 rounded"
                />
                <label htmlFor="mandatory" className="text-sm text-gray-300">
                  This is a mandatory field
                </label>
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-6 py-2 bg-dark-800 hover:bg-dark-700 rounded text-gray-300"
              >
                Cancel
              </button>
              <button
                onClick={handleAddTerm}
                className="btn-primary"
                disabled={!newTerm.business_name}
                data-testid="glossary-save-term-btn"
              >
                {editingTerm ? 'Update Term' : 'Add Term'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Upload CSV Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass border border-primary-500/30 rounded-xl p-6 max-w-lg w-full">
            <h2 className="text-2xl font-bold gradient-text mb-6">Import Glossary from CSV</h2>

            <div className="space-y-4">
              <div className="border-2 border-dashed border-dark-700 rounded-lg p-8 text-center hover:border-primary-500/50 transition-colors">
                <Upload className="w-12 h-12 text-gray-500 mx-auto mb-3" />
                <p className="text-gray-400 mb-2">Drop your CSV file here or click to browse</p>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => {
                    if (e.target.files?.[0]) {
                      importMutation.mutate(e.target.files[0])
                    }
                  }}
                  className="hidden"
                  id="csv-upload"
                />
                <label
                  htmlFor="csv-upload"
                  className="inline-block px-4 py-2 bg-primary-600/20 text-primary-400 rounded cursor-pointer hover:bg-primary-600/30"
                >
                  Choose File
                </label>
              </div>

              <div className="bg-dark-900 border border-dark-700 rounded p-4">
                <p className="text-sm font-medium text-gray-300 mb-2">Expected CSV Format:</p>
                <code className="text-xs text-gray-500 block">
                  Business Term, Technical Column, Data Type, Domain, Description, Mandatory, Owner
                </code>
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowUploadModal(false)}
                className="px-6 py-2 bg-dark-800 hover:bg-dark-700 rounded text-gray-300"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
