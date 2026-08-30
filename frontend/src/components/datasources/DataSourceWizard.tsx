/**
 * Data Source Wizard - 4-step wizard for adding new data sources
 * Steps: Choose Type → Basic Info → Connection Config → Test Connection
 */
import React, { useState, useEffect } from 'react';
import { X, Database, Cloud, Server, HardDrive, Check, AlertCircle, Loader2, ArrowLeft, ArrowRight } from 'lucide-react';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import datasourceService from '../../services/datasource';
import toast from 'react-hot-toast';

interface DataSourceWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editingDataSource?: {
    id: string;
    name: string;
    type: string;
    connection_config: Record<string, any>;
  };
}

interface ConnectionConfig {
  [key: string]: string | number | boolean;
}

interface DataSourceType {
  id: string;
  name: string;
  icon: React.ReactNode;
  description: string;
  category: 'database' | 'warehouse' | 'storage';
}

const dataSourceTypes: DataSourceType[] = [
  {
    id: 'postgresql',
    name: 'PostgreSQL',
    icon: <Database className="w-8 h-8" />,
    description: 'Open-source relational database',
    category: 'database'
  },
  {
    id: 'mysql',
    name: 'MySQL',
    icon: <Database className="w-8 h-8" />,
    description: 'Popular open-source database',
    category: 'database'
  },
  {
    id: 'snowflake',
    name: 'Snowflake',
    icon: <Cloud className="w-8 h-8" />,
    description: 'Cloud data warehouse',
    category: 'warehouse'
  },
  {
    id: 'databricks',
    name: 'Databricks',
    icon: <Server className="w-8 h-8" />,
    description: 'Unified analytics platform',
    category: 'warehouse'
  },
  {
    id: 'starburst',
    name: 'Starburst',
    icon: <Server className="w-8 h-8" />,
    description: 'Distributed SQL query engine',
    category: 'warehouse'
  },
  {
    id: 'azure_datalake',
    name: 'Azure Data Lake',
    icon: <Cloud className="w-8 h-8" />,
    description: 'Microsoft cloud storage',
    category: 'storage'
  },
  {
    id: 's3',
    name: 'AWS S3',
    icon: <HardDrive className="w-8 h-8" />,
    description: 'Amazon cloud object storage',
    category: 'storage'
  },
  {
    id: 'gcs',
    name: 'Google Cloud Storage',
    icon: <Cloud className="w-8 h-8" />,
    description: 'Google cloud storage',
    category: 'storage'
  }
];

export default function DataSourceWizard({ isOpen, onClose, onSuccess, editingDataSource }: DataSourceWizardProps) {
  const { currentWorkspace } = useWorkspace();
  const [currentStep, setCurrentStep] = useState(editingDataSource ? 2 : 1);
  const [selectedType, setSelectedType] = useState<string>(editingDataSource?.type || '');
  const [name, setName] = useState(editingDataSource?.name || '');
  const [description, setDescription] = useState('');
  const [config, setConfig] = useState<ConnectionConfig>(editingDataSource?.connection_config || {});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; details?: any } | null>(null);

  const resetWizard = () => {
    setCurrentStep(1);
    setSelectedType('');
    setName('');
    setDescription('');
    setConfig({});
    setTestResult(null);
  };

  // Update state when editingDataSource changes
  useEffect(() => {
    if (editingDataSource) {
      setCurrentStep(2);
      setSelectedType(editingDataSource.type);
      setName(editingDataSource.name);
      setConfig(editingDataSource.connection_config);
      setTestResult(null);
    } else if (!isOpen) {
      // Reset wizard when modal closes
      resetWizard();
    }
  }, [editingDataSource, isOpen]);

  if (!isOpen) return null;
  if (!currentWorkspace) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-dark-900 p-6 rounded-lg">
          <p className="text-red-400">Please select a workspace first</p>
        </div>
      </div>
    );
  }

  const handleTypeSelect = (typeId: string) => {
    setSelectedType(typeId);
    
    // Initialize config with default values for the selected type
    const defaults: Record<string, any> = {};
    
    switch (typeId) {
      case 'postgresql':
        defaults.port = 5432;
        defaults.ssl_mode = 'require';
        break;
      case 'mysql':
        defaults.port = 3306;
        defaults.ssl = false;
        break;
      case 'snowflake':
        break;
      case 'databricks':
        break;
      case 'starburst':
        defaults.port = 8080;
        break;
      case 's3':
        defaults.region = 'us-east-1';
        break;
      case 'gcs':
        break;
      case 'azure_datalake':
        break;
    }
    
    setConfig(defaults);
    
    // Auto-advance to next step after selecting type
    setCurrentStep(2);
  };

  const handleNext = () => {
    setCurrentStep(currentStep + 1);
  };

  const handleBack = () => {
    setCurrentStep(currentStep - 1);
    setTestResult(null); // Clear test result when going back
  };

  const handleConfigChange = (field: string, value: string | number | boolean) => {
    setConfig({ ...config, [field]: value });
  };

  const handleTestConnection = async () => {
    if (!currentWorkspace) return;
    
    setTesting(true);
    setTestResult(null);

    console.log('Testing connection with:', {
      orgId: currentWorkspace?.workspace_id.toString(),
      type: selectedType,
      connection_config: config
    });

    try {
      const result = await datasourceService.testConnectionConfig(currentWorkspace?.workspace_id.toString(), {
        type: selectedType,
        connection_config: config
      });

      if (result.success) {
        setTestResult({
          success: true,
          message: result.message || 'Connection successful!',
          details: result.details
        });
        setCurrentStep(3);
      } else {
        setTestResult({
          success: false,
          message: result.message || 'Connection failed. Please check your configuration.',
          details: result.details
        });
        setCurrentStep(3);
      }
    } catch (error: any) {
      console.error('Test connection error:', error);
      const errorMessage = error.response?.data?.detail 
        ? (typeof error.response.data.detail === 'string' 
          ? error.response.data.detail 
          : JSON.stringify(error.response.data.detail))
        : error.message || 'Network error. Please check your connection and try again.';
      
      setTestResult({
        success: false,
        message: errorMessage
      });
    } finally {
      setTesting(false);
    }
  };

  const handleCreate = async () => {
    if (!currentWorkspace) return;
    
    try {
      if (editingDataSource) {
        await datasourceService.update(currentWorkspace?.workspace_id.toString(), editingDataSource.id, {
          name,
          type: selectedType,
          connection_config: config
        });
      } else {
        await datasourceService.create(currentWorkspace?.workspace_id.toString(), {
          name,
          type: selectedType,
          connection_config: config
        });
      }

      onSuccess();
      resetWizard();
      onClose();
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail 
        ? (typeof error.response.data.detail === 'string' 
          ? error.response.data.detail 
          : JSON.stringify(error.response.data.detail))
        : 'Unknown error';
      toast.error(`Failed to ${editingDataSource ? 'update' : 'create'} data source: ${errorMessage}`);
    }
  };

  const renderConnectionFields = () => {
    const fields: { name: string; label: string; type: string; required: boolean; default?: any; options?: string[] }[] = [];

    switch (selectedType) {
      case 'postgresql':
        fields.push(
          { name: 'host', label: 'Host', type: 'text', required: true },
          { name: 'port', label: 'Port', type: 'number', required: true, default: 5432 },
          { name: 'database', label: 'Database', type: 'text', required: true },
          { name: 'username', label: 'Username', type: 'text', required: true },
          { name: 'password', label: 'Password', type: 'password', required: true },
          { name: 'ssl_mode', label: 'SSL Mode', type: 'select', required: true, default: 'require', options: ['disable', 'require', 'verify-ca', 'verify-full'] }
        );
        break;

      case 'mysql':
        fields.push(
          { name: 'host', label: 'Host', type: 'text', required: true },
          { name: 'port', label: 'Port', type: 'number', required: true, default: 3306 },
          { name: 'database', label: 'Database', type: 'text', required: true },
          { name: 'username', label: 'Username', type: 'text', required: true },
          { name: 'password', label: 'Password', type: 'password', required: true },
          { name: 'ssl', label: 'Use SSL', type: 'checkbox', required: false, default: false }
        );
        break;

      case 'snowflake':
        fields.push(
          { name: 'account', label: 'Account', type: 'text', required: true },
          { name: 'username', label: 'Username', type: 'text', required: true },
          { name: 'password', label: 'Password', type: 'password', required: true },
          { name: 'warehouse', label: 'Warehouse', type: 'text', required: true },
          { name: 'database', label: 'Database', type: 'text', required: true },
          { name: 'schema', label: 'Schema', type: 'text', required: false },
          { name: 'role', label: 'Role', type: 'text', required: false }
        );
        break;

      case 'databricks':
        fields.push(
          { name: 'server_hostname', label: 'Server Hostname', type: 'text', required: true },
          { name: 'http_path', label: 'HTTP Path', type: 'text', required: true },
          { name: 'access_token', label: 'Access Token', type: 'password', required: true }
        );
        break;

      case 'starburst':
        fields.push(
          { name: 'host', label: 'Host', type: 'text', required: true },
          { name: 'port', label: 'Port', type: 'number', required: true, default: 8080 },
          { name: 'catalog', label: 'Catalog', type: 'text', required: true },
          { name: 'schema', label: 'Schema', type: 'text', required: true },
          { name: 'username', label: 'Username', type: 'text', required: true },
          { name: 'password', label: 'Password', type: 'password', required: true }
        );
        break;

      case 'azure_datalake':
        fields.push(
          { name: 'account_name', label: 'Account Name', type: 'text', required: true },
          { name: 'account_key', label: 'Account Key', type: 'password', required: true },
          { name: 'filesystem', label: 'Filesystem', type: 'text', required: true },
          { name: 'directory_path', label: 'Directory Path', type: 'text', required: false }
        );
        break;

      case 's3':
        fields.push(
          { name: 'bucket', label: 'Bucket Name', type: 'text', required: true },
          { name: 'region', label: 'Region', type: 'select', required: true, options: ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-southeast-1', 'ap-northeast-1'] },
          { name: 'access_key', label: 'Access Key', type: 'text', required: true },
          { name: 'secret_key', label: 'Secret Key', type: 'password', required: true },
          { name: 'prefix', label: 'Prefix (Optional)', type: 'text', required: false }
        );
        break;

      case 'gcs':
        fields.push(
          { name: 'project_id', label: 'Project ID', type: 'text', required: true },
          { name: 'bucket_name', label: 'Bucket Name', type: 'text', required: true },
          { name: 'service_account_key', label: 'Service Account Key (JSON)', type: 'textarea', required: true }
        );
        break;
    }

    return (
      <div className="space-y-4">
        {fields.map((field) => (
          <div key={field.name}>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              {field.label} {field.required && <span className="text-red-500">*</span>}
            </label>
            {field.type === 'select' ? (
              <select
                value={(config[field.name] as string) || field.default || ''}
                onChange={(e) => handleConfigChange(field.name, e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                required={field.required}
              >
                <option value="">Select {field.label}</option>
                {field.options?.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            ) : field.type === 'checkbox' ? (
              <input
                type="checkbox"
                checked={(config[field.name] as boolean) || field.default || false}
                onChange={(e) => handleConfigChange(field.name, e.target.checked)}
                className="w-4 h-4 text-orange-500 bg-gray-700 border-gray-600 rounded focus:ring-orange-500"
              />
            ) : field.type === 'textarea' ? (
              <textarea
                value={(config[field.name] as string) || ''}
                onChange={(e) => handleConfigChange(field.name, e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-orange-500 font-mono text-sm"
                rows={6}
                required={field.required}
                placeholder="Paste JSON service account key..."
              />
            ) : (
              <input
                type={field.type}
                value={(config[field.name] as string | number) || field.default || ''}
                onChange={(e) => handleConfigChange(field.name, field.type === 'number' ? parseInt(e.target.value) : e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                required={field.required}
              />
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <h2 className="text-2xl font-bold text-white">{editingDataSource ? 'Edit Data Source' : 'Add Data Source'}</h2>
          <button
            onClick={() => { resetWizard(); onClose(); }}
            className="text-gray-400 hover:text-white"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Stepper */}
        <div className="flex items-center justify-center p-4 border-b border-gray-700">
          {(editingDataSource ? ['Configuration', 'Test Connection'] : ['Choose Type', 'Configuration', 'Test Connection']).map((step, index) => {
            const stepNumber = editingDataSource ? index + 2 : index + 1;
            return (
              <div key={step} className="flex items-center">
                <div className={`flex items-center justify-center w-8 h-8 rounded-full ${
                  stepNumber < currentStep ? 'bg-green-500' :
                  stepNumber === currentStep ? 'bg-orange-500' :
                  'bg-gray-600'
                }`}>
                  {stepNumber < currentStep ? (
                    <Check className="w-5 h-5 text-white" />
                  ) : (
                    <span className="text-white text-sm">{editingDataSource ? index + 1 : stepNumber}</span>
                  )}
                </div>
                <span className={`ml-2 text-sm ${
                  stepNumber <= currentStep ? 'text-white' : 'text-gray-500'
                }`}>
                  {step}
                </span>
                {index < (editingDataSource ? 1 : 2) && <div className="w-12 h-0.5 mx-2 bg-gray-600" />}
              </div>
            );
          })}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-96">
          {/* Step 1: Choose Type */}
          {currentStep === 1 && (
            <div>
              <h3 className="text-lg font-semibold text-white mb-4">Select Data Source Type</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {dataSourceTypes.map((type) => (
                  <button
                    key={type.id}
                    onClick={() => handleTypeSelect(type.id)}
                    className={`p-4 rounded-lg border-2 transition-all ${
                      selectedType === type.id
                        ? 'border-orange-500 bg-orange-500/10'
                        : 'border-gray-600 bg-gray-700 hover:border-gray-500'
                    }`}
                  >
                    <div className="flex flex-col items-center text-center space-y-2">
                      <div className={selectedType === type.id ? 'text-orange-500' : 'text-gray-400'}>
                        {type.icon}
                      </div>
                      <div className="text-white font-medium text-sm">{type.name}</div>
                      <div className="text-gray-400 text-xs">{type.description}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Configuration (merged Basic Info + Connection Config) */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-4">Basic Information</h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Name <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                      placeholder="e.g., Production Database"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Description
                    </label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                      rows={2}
                      placeholder="Optional description..."
                    />
                  </div>
                </div>
              </div>
              
              <div className="border-t border-gray-700 pt-4">
                <h3 className="text-lg font-semibold text-white mb-4">Connection Configuration</h3>
                {renderConnectionFields()}
              </div>
            </div>
          )}

          {/* Step 3: Test Connection */}
          {currentStep === 3 && (
            <div className="text-center">
              <h3 className="text-lg font-semibold text-white mb-4">Connection Test</h3>
              {testing ? (
                <div className="flex flex-col items-center space-y-4">
                  <Loader2 className="w-16 h-16 text-orange-500 animate-spin" />
                  <p className="text-gray-300">Testing connection...</p>
                </div>
              ) : testResult ? (
                <div className={`p-6 rounded-lg ${testResult.success ? 'bg-green-500/10 border-2 border-green-500' : 'bg-red-500/10 border-2 border-red-500'}`}>
                  {testResult.success ? (
                    <>
                      <Check className="w-16 h-16 text-green-500 mx-auto mb-4" />
                      <p className="text-green-400 text-xl font-semibold mb-2">{testResult.message}</p>
                      {testResult.details && (
                        <div className="mt-4 text-left bg-gray-800/50 p-4 rounded-md">
                          <p className="text-sm font-semibold text-gray-300 mb-2">Connection Details:</p>
                          <pre className="text-xs text-gray-400 overflow-auto max-h-32">
                            {JSON.stringify(testResult.details, null, 2)}
                          </pre>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
                      <p className="text-red-400 text-xl font-semibold mb-2">Connection Failed</p>
                      <div className="mt-3 text-left bg-gray-800/50 p-4 rounded-md">
                        <p className="text-sm text-gray-300 whitespace-pre-wrap">{testResult.message}</p>
                        {testResult.details && (
                          <pre className="text-xs text-red-400 mt-2 overflow-auto max-h-32">
                            {JSON.stringify(testResult.details, null, 2)}
                          </pre>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-700">
          <div>
            {currentStep > 1 && (
              <button
                onClick={handleBack}
                className="flex items-center px-4 py-2 text-gray-300 hover:text-white"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </button>
            )}
          </div>
          <div className="flex space-x-3">
            <button
              onClick={() => { resetWizard(); onClose(); }}
              className="px-4 py-2 border border-gray-600 rounded-md text-gray-300 hover:bg-gray-700"
            >
              Cancel
            </button>
            {currentStep === 1 && !editingDataSource && (
              <button
                onClick={handleNext}
                disabled={!selectedType}
                className="flex items-center px-4 py-2 bg-orange-500 text-white rounded-md hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
                <ArrowRight className="w-4 h-4 ml-2" />
              </button>
            )}
            {currentStep === 2 && (
              <button
                onClick={handleTestConnection}
                disabled={!name.trim() || testing}
                className="flex items-center px-4 py-2 bg-orange-500 text-white rounded-md hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Test Connection
              </button>
            )}
            {currentStep === 3 && testResult?.success && (
              <button
                onClick={handleCreate}
                className="flex items-center px-4 py-2 bg-green-500 text-white rounded-md hover:bg-green-600"
              >
                <Check className="w-4 h-4 mr-2" />
                {editingDataSource ? 'Update Data Source' : 'Create Data Source'}
              </button>
            )}
            {currentStep === 4 && testResult && !testResult.success && (
              <button
                onClick={handleTestConnection}
                disabled={testing}
                className="flex items-center px-4 py-2 bg-orange-500 text-white rounded-md hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
