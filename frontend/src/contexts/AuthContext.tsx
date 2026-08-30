import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authService, User, LoginRequest, RegisterRequest } from '../services/auth';

interface AuthContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  loading: boolean;
  isAuthenticated: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in
    const initAuth = async () => {
      const token = localStorage.getItem('access_token');
      if (token) {
        try {
          const currentUser = await authService.getCurrentUser();
          setUser(currentUser);
        } catch (error) {
          // Token might be expired, try to refresh
          try {
            await refreshToken();
          } catch (refreshError) {
            // Refresh failed, clear tokens and mark session as expired
            const hadToken = !!localStorage.getItem('access_token');
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            if (hadToken) {
              localStorage.setItem('session_expired', '1');
            }
          }
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const login = async (credentials: LoginRequest) => {
    const response = await authService.login(credentials);
    
    if (response.requires_mfa) {
      throw new Error('MFA_REQUIRED');
    }
    
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    setUser(response.user);

    // Prefetch primary workspace so the role stripe/badge render correctly on
    // the landing page immediately after login (non-platform-operator users).
    const pr = response.user?.platform_role ?? null;
    const isPlatformOp = pr === 'platform_admin' || pr === 'platform_viewer';
    if (!isPlatformOp && !localStorage.getItem('selected_workspace_id')) {
      try {
        const { listWorkspaces } = await import('../services/workspace');
        const resp = await listWorkspaces({ page_size: 1 });
        const first = resp.data.find((w) => w.status === 'active');
        if (first) localStorage.setItem('selected_workspace_id', first.workspace_id);
      } catch (err) {
        // Non-fatal: badge will fall back to 'unknown' until user visits hub.
        console.warn('Prefetch of primary workspace failed:', err);
      }
    }
  };

  const register = async (data: RegisterRequest) => {
    await authService.register(data);
    // Don't auto-login after registration, user needs to verify email
  };

  const logout = async () => {
    try {
      await authService.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setUser(null);
    }
  };

  const refreshToken = async () => {
    const refresh = localStorage.getItem('refresh_token');
    if (!refresh) {
      throw new Error('No refresh token');
    }

    const response = await authService.refreshToken(refresh);
    localStorage.setItem('access_token', response.access_token);
    
    // Get updated user info
    const currentUser = await authService.getCurrentUser();
    setUser(currentUser);
  };

  const value = {
    user,
    setUser,
    loading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
    refreshToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
