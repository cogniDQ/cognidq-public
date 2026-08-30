/**
 * TagInput — Enter to add, × to remove, comma-paste bulk, duplicate prevention
 */
import { useState, useCallback } from 'react'
import { X } from 'lucide-react'

interface TagInputProps {
  tags: string[]
  onChange: (tags: string[]) => void
  label?: string
  placeholder?: string
  disabled?: boolean
}

export function TagInput({
  tags,
  onChange,
  label,
  placeholder = 'Type and press Enter…',
  disabled = false,
}: TagInputProps) {
  const [input, setInput] = useState('')

  const addTags = useCallback((raw: string) => {
    const newTags = raw
      .split(',')
      .map(t => t.trim())
      .filter(t => t.length > 0 && !tags.includes(t))
    if (newTags.length > 0) {
      onChange([...tags, ...newTags])
    }
  }, [tags, onChange])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (input.trim()) {
        addTags(input)
        setInput('')
      }
    }
  }

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData('text')
    if (text.includes(',')) {
      e.preventDefault()
      addTags(text)
      setInput('')
    }
  }

  const removeTag = (tag: string) => {
    if (disabled) return
    onChange(tags.filter(t => t !== tag))
  }

  return (
    <div className="space-y-2">
      {label && (
        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</label>
      )}

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map(tag => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-dark-700 text-gray-300 text-xs rounded-full"
            >
              {tag}
              {!disabled && (
                <button type="button" onClick={() => removeTag(tag)} className="hover:text-red-400">
                  <X className="w-3 h-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Input */}
      <input
        type="text"
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:border-primary-500 focus:outline-none disabled:opacity-50"
      />
      <p className="text-xs text-gray-600">Press Enter to add. Paste comma-separated values for bulk add.</p>
    </div>
  )
}
