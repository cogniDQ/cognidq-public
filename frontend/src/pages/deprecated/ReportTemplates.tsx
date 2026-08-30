import React, { useState } from 'react';
import { OverviewDashboard } from '../../dashboards/OverviewDashboard';
import { FlowExecutionReport } from '../../dashboards/FlowExecutionReport';
import { FlowHistoryDashboard } from '../../dashboards/FlowHistoryDashboard';
import { DatasetQualityProfile } from '../../dashboards/DatasetQualityProfile';
import { CheckIntelligenceDashboard } from '../../dashboards/CheckIntelligenceDashboard';
import { AnomalyDetectionDashboard } from '../../dashboards/AnomalyDetectionDashboard';
import { IncidentSLADashboard } from '../../dashboards/IncidentSLADashboard';
import { AdoptionValueDashboard } from '../../dashboards/AdoptionValueDashboard';
import {
  ChartPieIcon,
  DocumentTextIcon,
  ClockIcon,
  CircleStackIcon,
  LightBulbIcon,
  BellAlertIcon,
  ShieldCheckIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';

type TabId =
  | 'overview'
  | 'flow-execution'
  | 'flow-history'
  | 'dataset-profile'
  | 'check-intelligence'
  | 'anomaly-detection'
  | 'incident-sla'
  | 'adoption-value';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
  description: string;
}

const tabs: Tab[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: <ChartPieIcon className="w-5 h-5" />,
    description: 'Coverage & Maturity Metrics',
  },
  {
    id: 'flow-execution',
    label: 'Flow Execution',
    icon: <DocumentTextIcon className="w-5 h-5" />,
    description: 'Single Run Analysis',
  },
  {
    id: 'flow-history',
    label: 'Flow History',
    icon: <ClockIcon className="w-5 h-5" />,
    description: 'Operational Intelligence',
  },
  {
    id: 'dataset-profile',
    label: 'Dataset Profile',
    icon: <CircleStackIcon className="w-5 h-5" />,
    description: 'Cross-Flow Dataset View',
  },
  {
    id: 'check-intelligence',
    label: 'Check Intelligence',
    icon: <LightBulbIcon className="w-5 h-5" />,
    description: 'Check Effectiveness Analysis',
  },
  {
    id: 'anomaly-detection',
    label: 'Anomaly Detection',
    icon: <BellAlertIcon className="w-5 h-5" />,
    description: 'Proactive Issue Detection',
  },
  {
    id: 'incident-sla',
    label: 'Incident & SLA',
    icon: <ShieldCheckIcon className="w-5 h-5" />,
    description: 'Enterprise Accountability',
  },
  {
    id: 'adoption-value',
    label: 'Adoption & ROI',
    icon: <ChartBarIcon className="w-5 h-5" />,
    description: 'Platform Value Metrics',
  },
];

const ReportTemplates: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  const renderDashboard = () => {
    switch (activeTab) {
      case 'overview':
        return <OverviewDashboard />;
      case 'flow-execution':
        return <FlowExecutionReport />;
      case 'flow-history':
        return <FlowHistoryDashboard />;
      case 'dataset-profile':
        return <DatasetQualityProfile />;
      case 'check-intelligence':
        return <CheckIntelligenceDashboard />;
      case 'anomaly-detection':
        return <AnomalyDetectionDashboard />;
      case 'incident-sla':
        return <IncidentSLADashboard />;
      case 'adoption-value':
        return <AdoptionValueDashboard />;
      default:
        return <OverviewDashboard />;
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-900/50 to-violet-900/50 border-b border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Report Templates</h1>
            <p className="text-sm text-gray-400">
              Preview all 8 dashboard templates — visualize and refine each report layout
            </p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-indigo-500/20 border border-indigo-500/40 rounded-lg">
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
            <span className="text-xs text-indigo-300 font-medium">Template Preview Mode</span>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-gray-800 border-b border-gray-700 overflow-x-auto">
        <div className="flex px-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600'
              }`}
            >
              {tab.icon}
              <div className="text-left">
                <div className="text-sm font-medium">{tab.label}</div>
                <div className="text-xs opacity-75">{tab.description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Dashboard Content */}
      <div className="flex-1 overflow-auto p-6">{renderDashboard()}</div>
    </div>
  );
};

export default ReportTemplates;
