/**
 * F134 P11 — Demo Request Service
 *
 * Wraps the public /demo-requests endpoint.
 */
import { api } from './api';

export interface DemoRequestPayload {
  first_name: string;
  last_name: string;
  email: string;
  company: string;
  use_case?: string;
  template_id?: string;
}

export interface DemoRequestResponse {
  id: string;
  status: string;
  email: string;
  company: string;
  created_at: string;
}

export const submitDemoRequest = async (
  payload: DemoRequestPayload,
): Promise<DemoRequestResponse> => {
  const { data } = await api.post<DemoRequestResponse>('/demo-requests', payload);
  return data;
};

export const getDemoRequestStatus = async (
  requestId: string,
): Promise<DemoRequestResponse> => {
  const { data } = await api.get<DemoRequestResponse>(`/demo-requests/${requestId}/status`);
  return data;
};
