interface RuleTextInputProps {
  value: string
  onChange: (value: string) => void
  maxLength: number
}

export default function RuleTextInput({ value, onChange, maxLength }: RuleTextInputProps) {
  const charCount = value.length
  const isOverLimit = charCount > maxLength

  return (
    <div>
      <label htmlFor="rule-text" className="block text-sm font-medium text-gray-300 mb-2">
        Business Rule
      </label>
      <textarea
        id="rule-text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder='Example: "Shipping date must be greater than or equal to order date"'
        className="textarea h-32 w-full"
        maxLength={maxLength}
        data-testid="rule-text-input"
      />
      <div className={`text-xs mt-1 text-right ${isOverLimit ? 'text-red-500' : 'text-gray-400'}`}>
        {charCount}/{maxLength}
      </div>
    </div>
  )
}
