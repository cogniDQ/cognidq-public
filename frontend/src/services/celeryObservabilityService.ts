/**
 * Celery / Flower observability service — F6
 *
 * Wraps platform-only endpoints under
 *   /api/v1/platform/celery
 */
import { api } from './api';

export interface CeleryHealth {
  status: 'ok' | 'degraded' | 'no-workers' | 'unavailable';
  detail?: string;
  workers_total: number;
  workers_online: number;
  broker_url?: string;
}

export interface CeleryWorker {
  name: string;
  status: boolean;
  active: any;
  processed: number | null;
  loadavg: number[] | null;
  pool: any;
  registered_tasks: string[];
}

export interface CeleryTask {
  id: string;
  name: string | null;
  state: string | null;
  received: number | null;
  started: number | null;
  succeeded: number | null;
  failed: number | null;
  runtime: number | null;
  exception: string | null;
  worker: string | null;
  args: string | null;
  kwargs: string | null;
}

export async function getCeleryHealth(): Promise<CeleryHealth> {
  const { data } = await api.get<CeleryHealth>('/platform/celery/health');
  return data;
}

export async function getCeleryWorkers(): Promise<{ workers: CeleryWorker[] }> {
  const { data } = await api.get('/platform/celery/workers');
  return data;
}

export async function getCeleryTasks(params: { limit?: number; state?: string } = {}): Promise<{ tasks: CeleryTask[]; total: number }> {
  const { data } = await api.get('/platform/celery/tasks', { params });
  return data;
}

export async function getCeleryQueues(): Promise<any> {
  const { data } = await api.get('/platform/celery/queues');
  return data;
}
