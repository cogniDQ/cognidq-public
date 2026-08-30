import { GitBranch, ChevronRight } from 'lucide-react'

interface ComponentLibraryProps {
  checks: any[]
  selectedCategory: string
  categories: Array<{ id: string; name: string; icon: any }>
  onCategorySelect: (categoryId: string) => void
  onCheckAdd: (check: any) => void
  isVisible: boolean
  onToggle: (visible: boolean) => void
}

export function ComponentLibrary({
  checks,
  selectedCategory,
  categories,
  onCategorySelect,
  onCheckAdd,
  isVisible,
  onToggle
}: ComponentLibraryProps) {
  if (!isVisible) {
    return (
      <button
        onClick={() => onToggle(true)}
        className="absolute left-0 top-1/2 -translate-y-1/2 z-50 glass px-2 py-6 border-r border-dark-800 hover:bg-dark-800 text-gray-400 hover:text-primary-400"
        title="Show library"
      >
        <GitBranch className="w-4 h-4" />
      </button>
    )
  }

  return (
    <div className="w-64 glass border-r border-dark-800 overflow-y-auto flex-shrink-0">
      <div className="p-3 border-b border-dark-800">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-200">DQ Check Library</h2>
          <button 
            onClick={() => onToggle(false)}
            className="p-1 hover:bg-dark-800 rounded text-gray-500 hover:text-gray-300"
            title="Hide library"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
        
        {/* Category Filters */}
        <div className="space-y-1">
          {categories.map(cat => {
            const Icon = cat.icon
            return (
              <button
                key={cat.id}
                onClick={() => onCategorySelect(cat.id)}
                className={`w-full flex items-center space-x-2 px-2 py-1.5 rounded text-xs transition-all ${
                  selectedCategory === cat.id
                    ? 'bg-primary-600/20 text-primary-400'
                    : 'text-gray-400 hover:bg-dark-800'
                }`}
              >
                <Icon className="w-3 h-3" />
                <span>{cat.name}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Check Components */}
      <div className="p-3 space-y-2">
        {checks.map(check => {
          const Icon = check.icon
          return (
            <div
              key={check.id}
              onClick={() => onCheckAdd(check)}
              className="card-hover p-2 cursor-pointer group"
            >
              <div className="flex items-start space-x-2">
                <div className={`w-6 h-6 rounded ${check.color} bg-opacity-20 flex items-center justify-center flex-shrink-0`}>
                  <Icon className="w-3 h-3 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-200 text-xs">{check.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{check.description}</p>
                  <div className="text-xs text-primary-400 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    + Add
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
