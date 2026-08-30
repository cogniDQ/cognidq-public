/**
 * AcceptInvitationPage — target of the acceptance URL emailed by the backend
 * (``{APP_PUBLIC_URL}/auth/accept-invitation?token=...``).
 *
 * Collects the invitee's email, password and optional name, then calls
 * ``authService.register`` with the invitation_token. After success the
 * user is redirected to the login page.
 */
import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Sparkles, CheckCircle, UserPlus } from 'lucide-react';

import { authService } from '../../services/auth';

export default function AcceptInvitationPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) setError('Missing invitation token in URL.');
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) return;
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await authService.register({
        email,
        password,
        full_name: fullName || undefined,
        invitation_token: token,
      });
      setSuccess(true);
    } catch (err) {
      const anyErr = err as { response?: { data?: { detail?: unknown } } };
      const detail = anyErr.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((d: { msg?: string }) => d.msg ?? '').filter(Boolean).join('; ')
        : typeof detail === 'string'
          ? detail
          : err instanceof Error
            ? err.message
            : 'Registration failed';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-dark-950 via-dark-900 to-dark-950 flex items-center justify-center px-4">
        <div className="max-w-md w-full glass rounded-lg border border-dark-700 p-8 text-center">
          <div className="w-16 h-16 bg-gradient-to-br from-accent-green to-accent-teal rounded-full mx-auto mb-4 flex items-center justify-center">
            <CheckCircle className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Invitation accepted</h2>
          <p className="text-gray-400 mb-6">
            Your account has been created. Sign in to access your tenant.
          </p>
          <button
            onClick={() => navigate('/auth/login')}
            className="inline-block py-3 px-6 bg-gradient-to-r from-primary-600 to-secondary-600 text-white rounded-lg"
          >
            Go to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-dark-950 via-dark-900 to-dark-950 flex items-center justify-center px-4">
      <div className="max-w-md w-full space-y-6 relative z-10">
        <div className="text-center">
          <div className="flex items-center justify-center space-x-3 mb-4">
            <Sparkles className="w-10 h-10 text-primary-500" />
          </div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400 mb-1">
            Accept Invitation
          </h1>
          <p className="text-gray-400 text-sm">Complete your account to join the tenant.</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="glass rounded-lg border border-dark-700 p-6 space-y-4"
          data-testid="accept-invitation-form"
        >
          {error && (
            <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-2 rounded text-sm">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 bg-dark-800/50 border border-dark-700 rounded text-white text-sm"
              data-testid="accept-email-input"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Full name (optional)</label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-2 bg-dark-800/50 border border-dark-700 rounded text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-dark-800/50 border border-dark-700 rounded text-white text-sm"
              data-testid="accept-password-input"
            />
            <p className="text-xs text-gray-500 mt-1">
              At least 8 characters with upper, lower and a digit.
            </p>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Confirm password</label>
            <input
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full px-3 py-2 bg-dark-800/50 border border-dark-700 rounded text-white text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={!token || submitting}
            className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-primary-600 to-secondary-600 text-white rounded-lg disabled:opacity-40"
            data-testid="accept-submit-btn"
          >
            <UserPlus className="w-4 h-4" />
            {submitting ? 'Creating account…' : 'Accept & create account'}
          </button>
          <p className="text-center text-sm text-gray-500">
            Already have an account? <Link to="/auth/login" className="text-primary-400 hover:text-primary-300">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
