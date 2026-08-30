/**
 * LLMConfigSection — workspace-level LLM provider configuration.
 *
 * Allows workspace admins and platform admins to configure the LLM provider,
 * API key, model, temperature, and max tokens used by AI features (e.g. NL Rule Builder).
 */
import { useState } from 'react';
import { CheckCircle, AlertTriangle } from 'lucide-react';
import type { LLMConfig, LLMConfigUpdate } from '../../../types/workspaceSettings';

interface Props {
  value: LLMConfig | null;
  canEdit: boolean;
  onSave: (update: LLMConfigUpdate) => Promise<void>;
}

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure_openai', label: 'Azure OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
];

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
  azure_openai: ['gpt-4o', 'gpt-4', 'gpt-35-turbo'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
};

export default function LLMConfigSection({ value, canEdit, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [provider, setProvider] = useState(value?.provider ?? 'openai');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState(value?.model ?? 'gpt-4o');
  const [temperature, setTemperature] = useState(value?.temperature ?? 0.0);
  const [maxTokens, setMaxTokens] = useState(value?.max_tokens ?? 4096);

  const isConfigured = value?.configured ?? false;

  const handleEdit = () => {
    setProvider(value?.provider ?? 'openai');
    setApiKey('');
    setModel(value?.model ?? 'gpt-4o');
    setTemperature(value?.temperature ?? 0.0);
    setMaxTokens(value?.max_tokens ?? 4096);
    setError(null);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setError(null);
  };

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider);
    const models = MODELS_BY_PROVIDER[newProvider] ?? [];
    if (models.length > 0 && !models.includes(model)) {
      setModel(models[0]);
    }
  };

  const handleSave = async () => {
    if (!apiKey.trim() && !isConfigured) {
      setError('API key is required.');
      return;
    }
    if (!model.trim()) {
      setError('Model is required.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const update: LLMConfigUpdate = {
        provider,
        api_key: apiKey.trim() || '__KEEP_EXISTING__',
        model: model.trim(),
        temperature,
        max_tokens: maxTokens,
      };
      // If user left api_key blank and config already exists, we still need to send the key
      // Backend requires a non-empty api_key; if editing existing config without changing key,
      // user must re-enter it.
      if (!apiKey.trim() && isConfigured) {
        setError('Please re-enter the API key to save changes.');
        setSaving(false);
        return;
      }
      await onSave(update);
      setEditing(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save LLM configuration.';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const availableModels = MODELS_BY_PROVIDER[provider] ?? [];

  return (
    <section
      className="rounded-2xl border border-dark-700 bg-dark-800/60 p-6"
      data-testid="llm-config-section"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white">LLM Configuration</h2>
          {isConfigured ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 text-xs font-medium">
              <CheckCircle className="w-3 h-3" />
              Configured
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-xs font-medium">
              <AlertTriangle className="w-3 h-3" />
              Not configured
            </span>
          )}
        </div>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
            data-testid="llm-config-edit-btn"
          >
            {isConfigured ? 'Edit' : 'Configure'}
          </button>
        )}
      </div>

      {!editing && (
        <div className="space-y-2 text-sm">
          {isConfigured ? (
            <>
              <div className="flex gap-2">
                <span className="text-gray-400 w-28">Provider:</span>
                <span className="text-white">{PROVIDERS.find((p) => p.value === value?.provider)?.label ?? value?.provider}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-28">API Key:</span>
                <span className="text-white font-mono">{value?.api_key_masked}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-28">Model:</span>
                <span className="text-white">{value?.model}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-28">Temperature:</span>
                <span className="text-white">{value?.temperature}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-400 w-28">Max Tokens:</span>
                <span className="text-white">{value?.max_tokens}</span>
              </div>
            </>
          ) : (
            <p className="text-gray-400">
              No LLM provider configured. AI features like the Natural Language Rule Builder
              will use the global server configuration. Configure a workspace-specific provider
              to use your own API key.
            </p>
          )}
        </div>
      )}

      {editing && (
        <div className="space-y-4">
          {/* Provider */}
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">Provider</span>
            <select
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
              data-testid="llm-provider-select"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          {/* API Key */}
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">
              API Key {isConfigured && <span className="text-amber-400">(re-enter to update)</span>}
            </span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={isConfigured ? '••••••••' : 'Enter API key'}
              className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none font-mono"
              autoComplete="off"
              data-testid="llm-api-key-input"
            />
          </label>

          {/* Model */}
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">Model</span>
            {availableModels.length > 0 ? (
              <select
                value={availableModels.includes(model) ? model : ''}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
                data-testid="llm-model-select"
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                {!availableModels.includes(model) && model && (
                  <option value={model}>{model} (custom)</option>
                )}
              </select>
            ) : (
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
                data-testid="llm-model-input"
              />
            )}
          </label>

          {/* Temperature */}
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">Temperature ({temperature})</span>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="w-full accent-indigo-500"
              data-testid="llm-temperature-input"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0 (Precise)</span>
              <span>2 (Creative)</span>
            </div>
          </label>

          {/* Max Tokens */}
          <label className="block">
            <span className="text-sm text-gray-400 mb-1 block">Max Tokens</span>
            <input
              type="number"
              min={1}
              max={16000}
              value={maxTokens}
              onChange={(e) => setMaxTokens(parseInt(e.target.value, 10) || 4096)}
              className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-white text-sm focus:border-indigo-500 focus:outline-none"
              data-testid="llm-max-tokens-input"
            />
          </label>

          {/* Error */}
          {error && (
            <p className="text-sm text-red-400" data-testid="llm-config-error">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
              data-testid="llm-config-save-btn"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-dark-700 hover:bg-dark-600 text-gray-300 text-sm font-medium transition-colors"
              data-testid="llm-config-cancel-btn"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
