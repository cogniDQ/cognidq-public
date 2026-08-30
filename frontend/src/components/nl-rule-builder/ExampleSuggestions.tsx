interface ExampleSuggestionsProps {
  onSelect: (text: string) => void
}

const EXAMPLES = [
  { label: 'Not null check', text: 'Customer email must not be null' },
  { label: 'Date comparison', text: 'Shipping date must be after order date' },
  { label: 'Value in list', text: 'Status must be one of OPEN, CLOSED, PENDING' },
  { label: 'Numeric range', text: 'Customer age must be between 18 and 120' },
  { label: 'Reference lookup', text: 'Country code must exist in the ISO country reference list' },
  { label: 'Cross-field', text: 'Invoice total must equal the sum of line item amounts' },
]

export default function ExampleSuggestions({ onSelect }: ExampleSuggestionsProps) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-400 uppercase mb-2">Try these examples:</p>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example, idx) => (
          <button
            key={idx}
            onClick={() => onSelect(example.text)}
            className="text-xs px-3 py-1.5 bg-dark-700 hover:bg-dark-600 hover:text-primary-400 text-gray-400 rounded-full transition-colors border border-dark-600 hover:border-primary-500"
            title={example.text}
          >
            {example.label}
          </button>
        ))}
      </div>
    </div>
  )
}
