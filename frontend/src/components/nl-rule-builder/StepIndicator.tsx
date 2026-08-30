import { Check } from 'lucide-react'

type UIStep = 1 | 2 | 3

interface StepIndicatorProps {
  currentStep: UIStep
}

const STEPS: { label: string; step: UIStep }[] = [
  { label: 'Input', step: 1 },
  { label: 'Review', step: 2 },
  { label: 'Confirm', step: 3 },
]

export default function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <nav aria-label="Progress" className="flex items-center justify-center gap-0">
      {STEPS.map(({ label, step }, idx) => {
        const isCompleted = step < currentStep
        const isActive = step === currentStep
        return (
          <div key={step} className="flex items-center">
            {/* Step bubble */}
            <div className="flex flex-col items-center">
              <div
                className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-colors',
                  isCompleted
                    ? 'bg-primary-600 border-primary-600 text-white'
                    : isActive
                      ? 'bg-dark-800 border-primary-500 text-primary-400'
                      : 'bg-dark-800 border-dark-600 text-gray-500',
                ].join(' ')}
                aria-current={isActive ? 'step' : undefined}
                data-testid={`step-bubble-${step}`}
              >
                {isCompleted ? <Check className="w-4 h-4" /> : step}
              </div>
              <span
                className={[
                  'mt-1 text-xs font-medium',
                  isActive ? 'text-primary-600' : isCompleted ? 'text-primary-500' : 'text-gray-400',
                ].join(' ')}
              >
                {label}
              </span>
            </div>

            {/* Connector line between steps */}
            {idx < STEPS.length - 1 && (
              <div
                className={[
                  'w-16 h-0.5 mx-1 mb-5 transition-colors',
                  step < currentStep ? 'bg-primary-600' : 'bg-dark-700',
                ].join(' ')}
                aria-hidden="true"
              />
            )}
          </div>
        )
      })}
    </nav>
  )
}
