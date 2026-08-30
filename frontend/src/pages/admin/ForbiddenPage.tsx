/**
 * ForbiddenPage — rendered when a user attempts to access a page that requires
 * a role or permission they do not have.
 *
 * F129 P05: replaced hardcoded "/admin/tenants" link with dynamic back-navigation.
 */
import { useNavigate } from 'react-router-dom';
import { ShieldOff } from 'lucide-react';

export default function ForbiddenPage() {
  const navigate = useNavigate();

  return (
    <div
      role="main"
      className="min-h-screen bg-dark-950 flex items-center justify-center px-6"
    >
      <div className="text-center space-y-6 max-w-md">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-red-500/10 border border-red-500/30">
          <ShieldOff className="w-10 h-10 text-red-400" aria-hidden="true" />
        </div>
        <h1 className="text-3xl font-bold text-white">Access Denied</h1>
        <p className="text-gray-400">
          You don't have permission to access this page.
        </p>
        <div className="flex justify-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="px-6 py-3 rounded-lg bg-gray-700 hover:bg-gray-600 text-white font-medium transition-colors"
          >
            Go Back
          </button>
          <button
            onClick={() => navigate('/hub')}
            className="px-6 py-3 rounded-lg bg-primary-600 hover:bg-primary-700 text-white font-medium transition-colors"
          >
            Go to DQ Hub
          </button>
        </div>
      </div>
    </div>
  );
}
