/**
 * F134 P12 — Sandbox User API Service
 *
 * Wraps GET /sandbox/me, GET /sandbox/onboarding,
 * POST /sandbox/onboarding/{step_id}/complete,
 * POST /sandbox/extension-request
 */
import { api } from './api';

export interface SandboxMeResponse {
  is_sandbox: boolean;
  banner?: {
    remaining_days: number;
    is_expired: boolean;
    flags: Record<string, boolean>;
    sandbox_id: string;
    status: string;
  };
}

export interface OnboardingStep {
  step_id: string;
  label: string;
  completed: boolean;
  completed_at?: string;
}

export interface OnboardingResponse {
  steps: OnboardingStep[];
  all_complete: boolean;
}

export const getSandboxMe = async (): Promise<SandboxMeResponse> => {
  const { data } = await api.get<SandboxMeResponse>('/sandbox/me');
  return data;
};

export const getSandboxOnboarding = async (): Promise<OnboardingResponse> => {
  const { data } = await api.get<OnboardingResponse>('/sandbox/onboarding');
  return data;
};

export const completeSandboxStep = async (stepId: string): Promise<void> => {
  await api.post(`/sandbox/onboarding/${stepId}/complete`);
};

export const requestSandboxExtension = async (message?: string): Promise<void> => {
  await api.post('/sandbox/extension-request', { message });
};
