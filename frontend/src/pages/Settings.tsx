import React, { useState } from 'react'
import { authService } from '../services/auth'
import { Copy, Check, Key, Trash2 } from 'lucide-react'

export default function Settings() {
  const [activeTab, setActiveTab] = useState<'password' | 'sessions' | 'tokens'>('password')
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  })
  const [sessions, setSessions] = useState<any[]>([])
  const [tokens, setTokens] = useState<any[]>([])
  const [newToken, setNewToken] = useState<string | null>(null)
  const [tokenForm, setTokenForm] = useState({
    name: '',
    expires_in_days: 30
  })
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setError('New passwords do not match')
      return
    }

    setLoading(true)
    try {
      await authService.changePassword({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password
      })
      setSuccess('Password changed successfully')
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' })
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  const loadSessions = async () => {
    setLoading(true)
    try {
      const data = await authService.getSessions()
      setSessions(data.sessions || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }

  const handleRevokeSession = async (sessionId: string) => {
    if (!confirm('Are you sure you want to revoke this session?')) return

    try {
      await authService.revokeSession(sessionId)
      setSuccess('Session revoked successfully')
      loadSessions()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to revoke session')
    }
  }

  const handleTabChange = (tab: 'password' | 'sessions' | 'tokens') => {
    setActiveTab(tab)
    setError('')
    setSuccess('')
    setNewToken(null)
    if (tab === 'sessions') {
      loadSessions()
    } else if (tab === 'tokens') {
      loadTokens()
    }
  }

  const loadTokens = async () => {
    setLoading(true)
    try {
      const data = await authService.getTokens()
      setTokens(data.tokens || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tokens')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateToken = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)

    try {
      const data = await authService.createToken(tokenForm)
      setNewToken(data.token)
      setSuccess('Token created successfully. Make sure to copy it now - you won\'t see it again!')
      setTokenForm({ name: '', expires_in_days: 30 })
      loadTokens()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create token')
    } finally {
      setLoading(false)
    }
  }

  const handleRevokeToken = async (tokenId: string) => {
    if (!confirm('Are you sure you want to revoke this token? This cannot be undone.')) return

    try {
      await authService.revokeToken(tokenId)
      setSuccess('Token revoked successfully')
      loadTokens()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to revoke token')
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-700">
          <h1 className="text-2xl font-bold text-white">Settings</h1>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-700">
          <nav className="flex px-6">
            <button
              onClick={() => handleTabChange('password')}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'password'
                  ? 'border-primary-500 text-primary-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Change Password
            </button>
            <button
              onClick={() => handleTabChange('sessions')}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'sessions'
                  ? 'border-primary-500 text-primary-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Active Sessions
            </button>
            <button
              onClick={() => handleTabChange('tokens')}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'tokens'
                  ? 'border-primary-500 text-primary-500'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              API Tokens
            </button>
          </nav>
        </div>

        {/* Content */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-lg text-red-200">
              {error}
            </div>
          )}

          {success && (
            <div className="mb-4 p-4 bg-green-900/50 border border-green-700 rounded-lg text-green-200">
              {success}
            </div>
          )}

          {activeTab === 'password' && (
            <form onSubmit={handlePasswordChange} className="space-y-6 max-w-md">
              <div>
                <label htmlFor="current_password" className="block text-sm font-medium text-gray-300 mb-2">
                  Current Password
                </label>
                <input
                  type="password"
                  id="current_password"
                  value={passwordForm.current_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  required
                />
              </div>

              <div>
                <label htmlFor="new_password" className="block text-sm font-medium text-gray-300 mb-2">
                  New Password
                </label>
                <input
                  type="password"
                  id="new_password"
                  value={passwordForm.new_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  required
                  minLength={8}
                />
                <p className="mt-1 text-xs text-gray-400">
                  Must be 8-128 characters with uppercase, lowercase, and numbers
                </p>
              </div>

              <div>
                <label htmlFor="confirm_password" className="block text-sm font-medium text-gray-300 mb-2">
                  Confirm New Password
                </label>
                <input
                  type="password"
                  id="confirm_password"
                  value={passwordForm.confirm_password}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Changing Password...' : 'Change Password'}
              </button>
            </form>
          )}

          {activeTab === 'sessions' && (
            <div className="space-y-4">
              {loading && sessions.length === 0 ? (
                <p className="text-gray-400">Loading sessions...</p>
              ) : sessions.length === 0 ? (
                <p className="text-gray-400">No active sessions found</p>
              ) : (
                <div className="space-y-3">
                  {sessions.map((session) => (
                    <div
                      key={session.id}
                      className="p-4 bg-gray-700 rounded-lg border border-gray-600 flex justify-between items-start"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-white font-medium">
                            {session.device_info?.user_agent?.split('/')[0] || 'Unknown Device'}
                          </h3>
                          {session.is_current && (
                            <span className="px-2 py-0.5 bg-green-900/50 text-green-200 text-xs rounded">
                              Current
                            </span>
                          )}
                        </div>
                        <div className="space-y-1 text-sm text-gray-400">
                          <p>IP: {session.ip_address || 'Unknown'}</p>
                          <p>Created: {new Date(session.created_at).toLocaleString()}</p>
                          <p>Expires: {new Date(session.expires_at).toLocaleString()}</p>
                        </div>
                      </div>
                      {!session.is_current && (
                        <button
                          onClick={() => handleRevokeSession(session.id)}
                          className="ml-4 px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'tokens' && (
            <div className="space-y-6">
              {/* Create Token Form */}
              <div className="bg-gray-700/50 rounded-lg border border-gray-600 p-6">
                <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <Key className="w-5 h-5" />
                  Create New Token
                </h2>
                
                {newToken && (
                  <div className="mb-4 p-4 bg-green-900/30 border border-green-700 rounded-lg">
                    <p className="text-sm text-green-200 mb-2 font-medium">
                      ⚠️ Make sure to copy your token now. You won't be able to see it again!
                    </p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 px-3 py-2 bg-dark-800 text-green-400 rounded text-sm font-mono break-all">
                        {newToken}
                      </code>
                      <button
                        onClick={() => copyToClipboard(newToken)}
                        className="px-3 py-2 bg-primary-600 hover:bg-primary-500 text-white rounded transition-colors flex items-center gap-2"
                      >
                        {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                        {copied ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  </div>
                )}
                
                <form onSubmit={handleCreateToken} className="space-y-4">
                  <div>
                    <label htmlFor="token-name" className="block text-sm font-medium text-gray-300 mb-2">
                      Token Name
                    </label>
                    <input
                      id="token-name"
                      type="text"
                      value={tokenForm.name}
                      onChange={(e) => setTokenForm({ ...tokenForm, name: e.target.value })}
                      className="w-full px-4 py-2 bg-dark-800/50 border border-dark-700 rounded-lg text-white focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      placeholder="e.g., Production API, CI/CD Pipeline"
                      required
                    />
                    <p className="mt-1 text-xs text-gray-400">
                      Choose a descriptive name to remember what this token is for
                    </p>
                  </div>

                  <div>
                    <label htmlFor="token-expiry" className="block text-sm font-medium text-gray-300 mb-2">
                      Expires In (days)
                    </label>
                    <select
                      id="token-expiry"
                      value={tokenForm.expires_in_days}
                      onChange={(e) => setTokenForm({ ...tokenForm, expires_in_days: parseInt(e.target.value) })}
                      className="w-full px-4 py-2 bg-dark-800/50 border border-dark-700 rounded-lg text-white focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                    >
                      <option value="7">7 days</option>
                      <option value="30">30 days</option>
                      <option value="60">60 days</option>
                      <option value="90">90 days</option>
                      <option value="180">180 days</option>
                      <option value="365">1 year</option>
                    </select>
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full px-4 py-2 bg-gradient-to-r from-primary-600 to-secondary-600 hover:from-primary-500 hover:to-secondary-500 text-white font-medium rounded-lg transition-all shadow-glow disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? 'Creating...' : 'Generate Token'}
                  </button>
                </form>
              </div>

              {/* Tokens List */}
              <div>
                <h2 className="text-lg font-semibold text-white mb-4">Active Tokens</h2>
                {loading && tokens.length === 0 ? (
                  <p className="text-gray-400">Loading tokens...</p>
                ) : tokens.length === 0 ? (
                  <p className="text-gray-400">No tokens found. Create one to get started!</p>
                ) : (
                  <div className="space-y-3">
                    {tokens.map((token) => (
                      <div
                        key={token.id}
                        className="p-4 bg-gray-700 rounded-lg border border-gray-600 flex justify-between items-start"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <h3 className="text-white font-medium">{token.name}</h3>
                            {token.is_valid && (
                              <span className="px-2 py-0.5 bg-green-900/50 text-green-200 text-xs rounded">
                                Active
                              </span>
                            )}
                            {!token.is_valid && (
                              <span className="px-2 py-0.5 bg-red-900/50 text-red-200 text-xs rounded">
                                Expired/Revoked
                              </span>
                            )}
                          </div>
                          <div className="space-y-1 text-sm text-gray-400">
                            <p className="font-mono">{token.prefix}...</p>
                            <p>Created: {new Date(token.created_at).toLocaleDateString()}</p>
                            {token.expires_at && (
                              <p>Expires: {new Date(token.expires_at).toLocaleDateString()}</p>
                            )}
                            {token.last_used_at ? (
                              <p>Last used: {new Date(token.last_used_at).toLocaleString()}</p>
                            ) : (
                              <p>Never used</p>
                            )}
                          </div>
                        </div>
                        {token.is_valid && (
                          <button
                            onClick={() => handleRevokeToken(token.id)}
                            className="ml-4 px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors flex items-center gap-1"
                          >
                            <Trash2 className="w-3 h-3" />
                            Revoke
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
