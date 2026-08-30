import React from 'react';
import { ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/24/solid';

interface KPICardProps {
  title: string;
  value: string | number;
  trend?: {
    value: number;
    direction: 'up' | 'down';
    label?: string;
  };
  icon?: React.ReactNode;
  subtitle?: string;
  status?: 'success' | 'warning' | 'error' | 'neutral';
}

export const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  trend,
  icon,
  subtitle,
  status = 'neutral',
}) => {
  const statusColors = {
    success: 'border-green-500 bg-green-500/10',
    warning: 'border-yellow-500 bg-yellow-500/10',
    error: 'border-red-500 bg-red-500/10',
    neutral: 'border-gray-700 bg-gray-800/50',
  };

  const trendColors = {
    up: 'text-green-500',
    down: 'text-red-500',
  };

  return (
    <div
      className={`border rounded-lg p-6 ${statusColors[status]} transition-all hover:shadow-lg`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            {icon && <div className="text-gray-400">{icon}</div>}
            <p className="text-sm text-gray-400">{title}</p>
          </div>
          <p className="text-3xl font-bold text-white mb-1">{value}</p>
          {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
        </div>
        {trend && (
          <div className="flex items-center gap-1">
            {trend.direction === 'up' ? (
              <ArrowUpIcon className={`w-4 h-4 ${trendColors.up}`} />
            ) : (
              <ArrowDownIcon className={`w-4 h-4 ${trendColors.down}`} />
            )}
            <span className={`text-sm font-medium ${trendColors[trend.direction]}`}>
              {trend.value}%
            </span>
            {trend.label && <span className="text-xs text-gray-500 ml-1">{trend.label}</span>}
          </div>
        )}
      </div>
    </div>
  );
};
