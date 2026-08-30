/**
 * CollapsibleSection — Chevron toggle, optional badge count, smooth animation
 */
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface CollapsibleSectionProps {
  title: string
  badge?: number | string
  defaultOpen?: boolean
  children: React.ReactNode
}

export function CollapsibleSection({
  title,
  badge,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full text-left group"
      >
        {isOpen ? (
          <ChevronDown className="w-4 h-4 text-gray-500 group-hover:text-gray-300 transition-colors" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500 group-hover:text-gray-300 transition-colors" />
        )}
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider group-hover:text-gray-300">
          {title}
        </span>
        {badge !== undefined && badge !== 0 && (
          <span className="px-1.5 py-0.5 bg-primary-500/20 text-primary-400 text-[10px] rounded-full font-medium">
            {badge}
          </span>
        )}
      </button>

      <div
        className={`overflow-hidden transition-all duration-200 ease-in-out ${
          isOpen ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="pl-6 space-y-3">
          {children}
        </div>
      </div>
    </div>
  )
}
