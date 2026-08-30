import React, { useState, useEffect } from 'react';
import { OverviewDashboard } from '../components/dashboards/OverviewDashboard';
import { FlowExecutionReport } from '../components/dashboards/FlowExecutionReport';
import { FlowHistoryDashboard } from '../components/dashboards/FlowHistoryDashboard';
import { DatasetQualityProfile } from '../components/dashboards/DatasetQualityProfile';
import { CheckIntelligenceDashboard } from '../components/dashboards/CheckIntelligenceDashboard';
import { AnomalyDetectionDashboard } from '../components/dashboards/AnomalyDetectionDashboard';
import { IncidentSLADashboard } from '../components/dashboards/IncidentSLADashboard';
import { AdoptionValueDashboard } from '../components/dashboards/AdoptionValueDashboard';
import {
  ChartPieIcon,
  DocumentTextIcon,
  ClockIcon,
  CircleStackIcon,
  LightBulbIcon,
  BellAlertIcon,
  ShieldCheckIcon,
  ChartBarIcon,
  ArrowDownTrayIcon,
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
    description: 'Single Run Analysis (Most Important)',
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

const Reports: React.FC = () => {
  console.log('🔵 Reports component rendering...');
  
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  useEffect(() => {
    console.log('✅ Reports component mounted!');
    return () => {
      console.log('❌ Reports component unmounted');
    };
  }, []);

  useEffect(() => {
    console.log('📊 Active tab changed to:', activeTab);
  }, [activeTab]);

  const handleExport = (format: 'pdf' | 'excel' | 'csv') => {
    console.log('📥 Exporting as:', format);
    alert(`Exporting ${activeTab} dashboard as ${format.toUpperCase()}...`);
  };

  const renderDashboard = () => {
    console.log('🎨 Rendering dashboard for tab:', activeTab);
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

  console.log('🔧 Rendering Reports component UI');
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 border-b border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Reports & Dashboards</h1>
            <p className="text-sm text-gray-400">
              Comprehensive data quality insights across 8 specialized views
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleExport('pdf')}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium flex items-center gap-2 transition-colors"
            >
              <ArrowDownTrayIcon className="w-5 h-5" />
              Export PDF
            </button>
            <button
              onClick={() => handleExport('excel')}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium flex items-center gap-2 transition-colors"
            >
              <ArrowDownTrayIcon className="w-5 h-5" />
              Export Excel
            </button>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-gray-800 border-b border-gray-700 overflow-x-auto">
        <div className="flex px-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                console.log('🖱️ Tab clicked:', tab.id);
                setActiveTab(tab.id);
              }}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-400'
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

      {/* Footer Info */}
      <div className="border-t border-gray-700 px-6 py-4 bg-gray-800">
        <div className="flex items-center justify-between text-sm text-gray-400">
          <div>
            <span className="font-medium text-white">Active Dashboard:</span> {tabs.find((t) => t.id === activeTab)?.label}
          </div>
          <div>
            Last updated: {new Date().toLocaleTimeString()} | Auto-refresh: Every 5 min
          </div>
        </div>
      </div>
    </div>
  );
};

export default Reports;
