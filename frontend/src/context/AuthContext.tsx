import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { User } from '../types/contract';
import * as authApi from '../services/auth';
import { setSessionExpiredHandler } from '../services/http';
import { clearPreviewCache } from '../services/sessions';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<User | null>(null);

  const signOutLocally = useCallback(() => {
    clearPreviewCache();
    setUser(null);
    setStatus('anonymous');
  }, []);

  // Restore the session from the httpOnly refresh cookie on first load.
  useEffect(() => {
    let cancelled = false;
    // A transient failure (rate limit, server restarting, network) is retried a few times
    // before giving up to the sign-in page; only a definite "no session" signs out at once.
    (async () => {
      for (let attempt = 0; attempt < 4 && !cancelled; attempt++) {
        try {
          const auth = await authApi.restoreSession();
          if (cancelled) return;
          if (auth) {
            setUser(auth.user);
            setStatus('authenticated');
          } else {
            setStatus('anonymous');
          }
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
        }
      }
      if (!cancelled) setStatus('anonymous');
    })();
    setSessionExpiredHandler(signOutLocally);
    return () => {
      cancelled = true;
      setSessionExpiredHandler(null);
    };
  }, [signOutLocally]);

  const login = useCallback(async (email: string, password: string) => {
    const auth = await authApi.login(email, password);
    setUser(auth.user);
    setStatus('authenticated');
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const auth = await authApi.register(email, password);
    setUser(auth.user);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    signOutLocally();
  }, [signOutLocally]);

  const value = useMemo(() => ({ status, user, login, register, logout }), [status, user, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
