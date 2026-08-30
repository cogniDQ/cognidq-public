import axios, { AxiosInstance } from 'axios';

// Use VITE_API_URL if set; fall back to the Vite proxy base path (relative).
// An empty string is falsy, so we use a nullish-coalescing check instead of ||
const API_URL = import.meta.env.VITE_API_URL || '/api/v1';

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
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

// Response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Skip refresh logic for auth endpoints (login/register return 401 for invalid credentials)
    const isAuthEndpoint = originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/register');

    // If error is 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
          throw new Error('No refresh token');
        }

        const response = await axios.post(`${API_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const { access_token } = response.data;
        localStorage.setItem('access_token', access_token);

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/auth/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Types
export interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  email_verified: boolean;
  status: string;
  last_login_at: string | null;
  created_at: string;
  platform_role?: string | null;
  tenant_id?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  requires_mfa: boolean;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
  invitation_token?: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  full_name: string | null;
  message: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface MessageResponse {
  message: string;
  success: boolean;
}

export interface UpdateProfileRequest {
  full_name?: string;
  avatar_url?: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}

export interface SessionInfo {
  id: string;
  device_info: any;
  ip_address: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface SessionListResponse {
  sessions: SessionInfo[];
  total: number;
}

// Auth Service
export const authService = {
  // Register new user
  async register(data: RegisterRequest): Promise<RegisterResponse> {
    const response = await api.post('/auth/register', data);
    return response.data;
  },

  // Login
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await api.post('/auth/login', credentials);
    return response.data;
  },

  // Logout
  async logout(): Promise<MessageResponse> {
    const response = await api.post('/auth/logout');
    return response.data;
  },

  // Refresh token
  async refreshToken(refreshToken: string): Promise<TokenResponse> {
    const response = await api.post('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },

  // Get current user
  async getCurrentUser(): Promise<User> {
    const response = await api.get('/auth/me');
    return response.data;
  },

  // Update profile
  async updateProfile(data: UpdateProfileRequest): Promise<User> {
    const response = await api.put('/auth/me', data);
    return response.data;
  },

  // Change password
  async changePassword(data: ChangePasswordRequest): Promise<MessageResponse> {
    const response = await api.post('/auth/change-password', data);
    return response.data;
  },

  // Request password reset
  async requestPasswordReset(data: PasswordResetRequest): Promise<MessageResponse> {
    const response = await api.post('/auth/password-reset/request', data);
    return response.data;
  },

  // Confirm password reset
  async confirmPasswordReset(data: PasswordResetConfirm): Promise<MessageResponse> {
    const response = await api.post('/auth/password-reset/confirm', data);
    return response.data;
  },

  // Verify email
  async verifyEmail(token: string): Promise<MessageResponse> {
    const response = await api.get(`/auth/verify-email/${token}`);
    return response.data;
  },

  // Get sessions
  async getSessions(): Promise<SessionListResponse> {
    const response = await api.get('/auth/sessions');
    return response.data;
  },

  // Revoke session
  async revokeSession(sessionId: string): Promise<MessageResponse> {
    const response = await api.delete(`/auth/sessions/${sessionId}`);
    return response.data;
  },

  // Get tokens
  async getTokens(): Promise<any> {
    const response = await api.get('/tokens');
    return response.data;
  },

  // Create token
  async createToken(data: { name: string; expires_in_days?: number }): Promise<any> {
    const response = await api.post('/tokens', data);
    return response.data;
  },

  // Revoke token
  async revokeToken(tokenId: string): Promise<MessageResponse> {
    const response = await api.delete(`/tokens/${tokenId}`);
    return response.data;
  },
};

export default api;
