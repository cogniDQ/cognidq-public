import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add request interceptor to include auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle auth errors
let isRefreshing = false;
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach(prom => {
    if (token) prom.resolve(token);
    else prom.reject(error);
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // F134 P12 — trial_expired: redirect sandbox users to expired page
    if (error.response?.status === 402) {
      const code = error.response?.data?.error?.code ?? error.response?.data?.code;
      if (code === 'trial_expired') {
        window.location.href = '/trial-expired';
        return Promise.reject(error);
      }
    }

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/refresh')
    ) {
      // Anonymous public-route calls: if there was never an access token,
      // don't redirect to /auth/login. Public pages stay usable.
      const hadAccessToken = !!localStorage.getItem('access_token');
      const hadRefreshToken = !!localStorage.getItem('refresh_token');
      if (!hadAccessToken && !hadRefreshToken) {
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(api(originalRequest));
            },
            reject,
          });
        });
      }
      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const resp = await api.post('/auth/refresh', { refresh_token: refreshToken });
          const newToken = resp.data.access_token;
          localStorage.setItem('access_token', newToken);
          if (resp.data.refresh_token) {
            localStorage.setItem('refresh_token', resp.data.refresh_token);
          }
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          processQueue(null, newToken);
          return api(originalRequest);
        } catch (refreshError) {
          processQueue(refreshError, null);
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/auth/login';
          return Promise.reject(refreshError);
        } finally {
          isRefreshing = false;
        }
      } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/auth/login';
      }
    }
    return Promise.reject(error);
  }
);

// Types
export interface ParsedPrompt {
  original_prompt: string
  entities: string[]
  conditions: string[]
  intent: string
  category: string
  confidence: number
  requires_clarification: boolean
  clarification_questions?: string[]
}

export interface ColumnMapping {
  business_term: string
  physical_column: string
  mapping_type: string
  mapped_value?: string
  condition?: string
  confidence: number
  glossary_term_id?: string
}

export interface GeneratedRule {
  rule_id: string
  rule_name: string
  description: string
  original_prompt: string
  sql: string
  pyspark?: string
  severity: string
  category: string
  metadata: any
}

export interface DataSource {
  connection_id: string
  type: 'postgresql' | 'mysql' | 'snowflake' | 'databricks' | 'spark'
  database: string
  schema_name?: string
  table: string
}

// API functions
export const parsePrompt = async (prompt: string): Promise<{
  parsed: ParsedPrompt
  suggested_mappings?: ColumnMapping[]
}> => {
  const response = await api.post('/rules/parse', { prompt })
  return response.data
}

export const generateRule = async (
  prompt: string,
  datasource: DataSource,
  severity: string = 'ERROR',
  column_mappings?: ColumnMapping[]
): Promise<{
  rule: GeneratedRule
  preview_sql: string
}> => {
  const response = await api.post('/rules/generate', {
    prompt,
    datasource,
    severity,
    column_mappings,
  })
  return response.data
}

export const searchGlossary = async (query: string, domain?: string) => {
  const response = await api.post('/glossary/search', {
    query,
    domain,
    limit: 10,
  })
  return response.data
}

export const listDomains = async () => {
  const response = await api.get('/glossary/domains')
  return response.data
}


