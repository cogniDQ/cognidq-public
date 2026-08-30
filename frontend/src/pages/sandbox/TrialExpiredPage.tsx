/**
 * F134 P12 — Trial Expired Page
 *
 * Shown when the sandbox token has a trial_expired error.
 * The axios response interceptor redirects here on 402 trial_expired responses.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Clock, Mail } from 'lucide-react';

export default function TrialExpiredPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="card max-w-md w-full text-center space-y-6 p-10">
        <div className="mx-auto w-16 h-16 rounded-full bg-orange-900/40 border border-orange-700 flex items-center justify-center">
          <Clock className="w-8 h-8 text-orange-400" />
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-white">Trial Expired</h1>
          <p className="text-gray-400 text-sm leading-relaxed">
            Your sandbox trial period has ended. Your data is safe and preserved.
            To continue, request an extension or speak to our team.
          </p>
        </div>

        <div className="flex flex-col space-y-3">
          <Link
            to="/auth/login"
            className="btn btn-primary flex items-center justify-center space-x-2"
          >
            <Mail className="w-4 h-4" />
            <span>Contact us about extending access</span>
          </Link>
          <Link to="/auth/login" className="btn btn-secondary text-sm">
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
