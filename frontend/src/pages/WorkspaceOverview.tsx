import React from 'react';
import { Link, useParams } from 'react-router-dom';
import { Database, BookOpen, GitBranch, FileCode, ArrowRight, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { useTenantScopedPath } from '../hooks/useTenantScopedPath';
import reportingService from '../services/reportingService';

const WorkspaceOverview: React.FC = () => {
  const { workspace_id: urlWorkspaceId } = useParams();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = urlWorkspaceId || currentWorkspace?.workspace_id;
  const { wsPath, tenantPath } = useTenantScopedPath();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['workspace-stats', workspaceId],
    queryFn: () => reportingService.getWorkspaceStats(workspaceId!),
    enabled: !!workspaceId,
    staleTime: 30_000,
  });

  const wsBase = workspaceId ? wsPath(workspaceId) : '/hub';

  const features = [
    {
      icon: Database,
      title: 'Connections',
      description: 'Connect and manage your data sources. Configure databases, data lakes, and file sources.',
      link: tenantPath('/connections'),
      color: 'from-blue-600 to-cyan-600',
    },
    {
      icon: BookOpen,
      title: 'Glossary',
      description: 'Define business glossary terms and map them to your data sources for consistency.',
      link: workspaceId ? wsPath(workspaceId, '/glossary') : '/hub',
      color: 'from-purple-600 to-pink-600',
    },
    {
      icon: GitBranch,
      title: 'Flows',
      description: 'Create visual data quality workflows with drag-and-drop components.',
      link: workspaceId ? wsPath(workspaceId, '/flows') : '/hub',
      color: 'from-green-600 to-teal-600',
    },
    {
      icon: FileCode,
      title: 'NL Rule Builder',
      description: 'Build data quality rules using AI-powered natural language.',
      link: `${wsBase}/nl-rule-builder`,
      color: 'from-orange-600 to-red-600',
    },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold text-content">Workspace Overview</h1>
        <p className="text-xl text-content-muted">
          Your central workspace for data quality management
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-12">
        {features.map((feature) => (
          <Link
            key={feature.title}
            to={feature.link}
            className="group bg-gray-800 rounded-xl p-6 border border-gray-700 hover:border-gray-600 transition-all hover:shadow-xl hover:shadow-purple-500/10"
          >
            <div className="flex items-start space-x-4">
              <div className={`w-12 h-12 rounded-lg bg-gradient-to-r ${feature.color} flex items-center justify-center flex-shrink-0`}>
                <feature.icon className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-xl font-semibold text-content">{feature.title}</h3>
                  <ArrowRight className="w-5 h-5 text-content-muted group-hover:text-content group-hover:translate-x-1 transition-all" />
                </div>
                <p className="text-content-muted">{feature.description}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-12">
        {[
          { label: 'Data Sources', value: stats?.datasource_count },
          { label: 'Glossary Terms', value: stats?.glossary_count },
          { label: 'Active Flows', value: stats?.flow_count },
          { label: 'Quality Rules', value: stats?.rule_count },
        ].map((stat) => (
          <div key={stat.label} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-content mb-2">
              {statsLoading ? (
                <Loader2 className="w-6 h-6 animate-spin text-content-muted" />
              ) : (
                stat.value ?? 0
              )}
            </div>
            <div className="text-sm text-content-muted">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="bg-gradient-to-r from-purple-900/20 to-blue-900/20 border border-purple-500/30 rounded-xl p-8 mt-12">
        <h2 className="text-2xl font-bold text-content mb-4">Getting Started</h2>
        <div className="space-y-3 text-content-muted">
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

export default WorkspaceOverview;
