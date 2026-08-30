/**
 * DQ Hub Welcome/Dashboard Page
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Database, BookOpen, GitBranch, FileCode, FileCheck, ArrowRight, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '../contexts/WorkspaceContext';
import reportingService from '../services/reportingService';

const DQHubWelcome: React.FC = () => {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.workspace_id;

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['workspace-stats', workspaceId],
    queryFn: () => reportingService.getWorkspaceStats(workspaceId!),
    enabled: !!workspaceId,
    staleTime: 30_000,
  });

  const features = [
    {
      icon: Database,
      title: 'Data Sources',
      description: 'Connect and manage your data sources. Configure databases, data lakes, and file sources.',
      link: '/hub/datasources',
      color: 'from-blue-600 to-cyan-600',
    },
    {
      icon: BookOpen,
      title: 'Definitions',
      description: 'Define business glossary terms and map them to your data sources for consistency.',
      link: '/hub/glossary',
      color: 'from-purple-600 to-pink-600',
    },
    {
      icon: GitBranch,
      title: 'Flow Builder',
      description: 'Create visual data quality workflows with drag-and-drop components.',
      link: '/hub/flow-builder',
      color: 'from-green-600 to-teal-600',
    },
    {
      icon: FileCode,
      title: 'Rule Builder',
      description: 'Build data quality rules using AI-powered natural language or manual configuration.',
      link: '/hub/rule-builder',
      color: 'from-orange-600 to-red-600',
    },
    {
      icon: FileCheck,
      title: 'Proposals',
      description: 'Review and approve AI-generated data quality rule proposals.',
      link: '/hub/proposals',
      color: 'from-yellow-600 to-amber-600',
    },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold text-white">Welcome to DQ Hub</h1>
        <p className="text-xl text-gray-400">
          Your central workspace for data quality management
        </p>
      </div>

      {/* Feature Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-12">
        {features.map((feature) => (
          <Link
            key={feature.link}
            to={feature.link}
            className="group bg-gray-800 rounded-xl p-6 border border-gray-700 hover:border-gray-600 transition-all hover:shadow-xl hover:shadow-purple-500/10"
          >
            <div className="flex items-start space-x-4">
              <div className={`w-12 h-12 rounded-lg bg-gradient-to-r ${feature.color} flex items-center justify-center flex-shrink-0`}>
                <feature.icon className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-semibold text-white">{feature.title}</h3>
                  <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-white group-hover:translate-x-1 transition-all" />
                </div>
                <p className="text-gray-400">{feature.description}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-12">
        {[
          { label: 'Data Sources', value: stats?.datasource_count },
          { label: 'Glossary Terms', value: stats?.glossary_count },
          { label: 'Active Flows', value: stats?.flow_count },
          { label: 'Quality Rules', value: stats?.rule_count },
        ].map((stat) => (
          <div key={stat.label} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-white mb-2">
              {statsLoading ? (
                <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
              ) : (
                stat.value ?? 0
              )}
            </div>
            <div className="text-sm text-gray-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Getting Started */}
      <div className="bg-gradient-to-r from-purple-900/20 to-blue-900/20 border border-purple-500/30 rounded-xl p-8 mt-12">
        <h2 className="text-2xl font-bold text-white mb-4">Getting Started</h2>
        <div className="space-y-3 text-gray-300">
          <div className="flex items-start space-x-3">
            <span className="text-purple-400 font-bold">1.</span>
            <span>Connect your first data source to start monitoring data quality</span>
          </div>
          <div className="flex items-start space-x-3">
            <span className="text-purple-400 font-bold">2.</span>
            <span>Define business terms in the glossary for consistency</span>
          </div>
          <div className="flex items-start space-x-3">
            <span className="text-purple-400 font-bold">3.</span>
            <span>Build your first data quality rule using AI or visual builder</span>
          </div>
          <div className="flex items-start space-x-3">
            <span className="text-purple-400 font-bold">4.</span>
            <span>Create flows to automate quality checks across your data pipeline</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DQHubWelcome;
