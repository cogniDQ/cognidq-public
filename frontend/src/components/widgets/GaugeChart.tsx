import React from 'react';

interface GaugeChartProps {
  value: number; // 0-100
  title?: string;
  label?: string;
  thresholds?: {
    good: number; // e.g., 80
    warning: number; // e.g., 60
  };
}

export const GaugeChart: React.FC<GaugeChartProps> = ({
  value,
  title,
  label,
  thresholds = { good: 80, warning: 60 },
}) => {
  const clampedValue = Math.max(0, Math.min(100, value));
  const rotation = (clampedValue / 100) * 180 - 90;

  const getColor = () => {
    if (clampedValue >= thresholds.good) return '#10B981';
    if (clampedValue >= thresholds.warning) return '#F59E0B';
    return '#EF4444';
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      {title && <h3 className="text-lg font-semibold text-white mb-4 text-center">{title}</h3>}
      <div className="relative w-48 h-24 mx-auto">
        {/* Gauge background */}
        <svg viewBox="0 0 200 100" className="w-full h-full">
          {/* Background arc */}
          <path
            d="M 20 90 A 80 80 0 0 1 180 90"
            fill="none"
            stroke="#374151"
            strokeWidth="20"
            strokeLinecap="round"
          />
          {/* Colored arc */}
          <path
            d="M 20 90 A 80 80 0 0 1 180 90"
            fill="none"
            stroke={getColor()}
            strokeWidth="20"
            strokeLinecap="round"
            strokeDasharray={`${(clampedValue / 100) * 251.2} 251.2`}
          />
          {/* Needle */}
          <line
            x1="100"
            y1="90"
            x2="100"
            y2="30"
            stroke="white"
            strokeWidth="3"
            strokeLinecap="round"
            transform={`rotate(${rotation} 100 90)`}
          />
          {/* Center dot */}
          <circle cx="100" cy="90" r="6" fill="white" />
        </svg>
      </div>
      <div className="text-center mt-4">
        <p className="text-3xl font-bold text-white">{clampedValue}%</p>
        {label && <p className="text-sm text-gray-400 mt-1">{label}</p>}
      </div>
    </div>
  );
};
