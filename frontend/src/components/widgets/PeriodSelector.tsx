import React from 'react';

interface PeriodSelectorProps {
  value: string;
  onChange: (period: string) => void;
  options?: { value: string; label: string }[];
}

const DEFAULT_OPTIONS = [
  { value: '7d', label: '7 Days' },
  { value: '30d', label: '30 Days' },
  { value: '90d', label: '90 Days' },
];

export const PeriodSelector: React.FC<PeriodSelectorProps> = ({
  value,
  onChange,
  options = DEFAULT_OPTIONS,
}) => (
  <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
    {options.map((opt) => (
      <button
        key={opt.value}
        onClick={() => onChange(opt.value)}
        className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
          value === opt.value
            ? 'bg-blue-600 text-white'
            : 'text-gray-400 hover:text-white hover:bg-gray-700'
        }`}
      >
        {opt.label}
      </button>
    ))}
  </div>
);
