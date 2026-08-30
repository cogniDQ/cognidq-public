/**
 * F134 P12 — SandboxBanner
 *
 * Shown at the top of the workspace layout when the user is in a sandbox.
 * Displays remaining days + extension request button.
 */
import React, { useEffect, useState } from 'react';
import { AlertTriangle, Clock, RefreshCw, X } from 'lucide-react';
import {
  getSandboxMe,
  requestSandboxExtension,
  type SandboxMeResponse,
} from '../../services/sandboxUserService';

export default function SandboxBanner() {
  const [data, setData] = useState<SandboxMeResponse | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [extending, setExtending] = useState(false);
  const [extendDone, setExtendDone] = useState(false);

  useEffect(() => {
    getSandboxMe()
      .then(setData)
      .catch(() => {/* not in a sandbox context — silent */});
  }, []);

  if (!data?.is_sandbox || !data.banner || dismissed) return null;

  const { remaining_days, is_expired } = data.banner;

  const handleExtend = async () => {
    const message = window.prompt('Optional message for your extension request:') ?? '';
    setExtending(true);
    try {
      await requestSandboxExtension(message);
      setExtendDone(true);
    } finally {
      setExtending(false);
    }
  };

  const urgency =
    is_expired || remaining_days <= 0
      ? 'bg-red-900/70 border-red-700'
      : remaining_days <= 3
      ? 'bg-orange-900/60 border-orange-700'
      : 'bg-yellow-900/40 border-yellow-700';

  return (
    <div
      data-testid="sandbox-banner"
      className={`flex items-center justify-between px-4 py-2 border-b text-sm ${urgency}`}
    >
      <div className="flex items-center space-x-2">
        {is_expired || remaining_days <= 0 ? (
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
        ) : (
          <Clock className="w-4 h-4 text-yellow-400 shrink-0" />
        )}
        <span className="text-gray-200">
          {is_expired || remaining_days <= 0
            ? 'Your sandbox trial has expired.'
            : `Sandbox trial — ${remaining_days} day${remaining_days === 1 ? '' : 's'} remaining.`}
        </span>
      </div>

      <div className="flex items-center space-x-3">
        {!extendDone ? (
          <button
            onClick={handleExtend}
            disabled={extending}
            className="flex items-center space-x-1 text-xs px-3 py-1 rounded bg-primary-700/60 hover:bg-primary-700 text-primary-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${extending ? 'animate-spin' : ''}`} />
            <span>{extending ? 'Sending…' : 'Request extension'}</span>
          </button>
        ) : (
          <span className="text-xs text-green-400">Extension requested ✓</span>
        )}
        {!is_expired && (
          <button
            onClick={() => setDismissed(true)}
            className="text-gray-500 hover:text-gray-300 transition-colors"
            title="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
