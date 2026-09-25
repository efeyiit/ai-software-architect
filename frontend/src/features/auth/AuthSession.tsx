import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { authApi, AuthApiError, type Session } from './api';

export type AuthState = { status: 'loading' | 'signed-out' } | { status: 'signed-in'; session: Session } |
  { status: 'error'; error: AuthApiError };
type AuthContextValue = { state: AuthState; retry: () => void; logout: () => Promise<void>; loggingOut: boolean; logoutError: string };
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  useEffect(() => {
    let active = true;
    setState({ status: 'loading' });
    authApi.session().then((session) => {
      if (active) setState(session ? { status: 'signed-in', session } : { status: 'signed-out' });
    }).catch((error: unknown) => {
      if (active) setState({ status: 'error', error: error instanceof AuthApiError ? error : new AuthApiError('failed', 'Oturum doğrulanamadı.') });
    });
    return () => { active = false; };
  }, [attempt]);

  async function logout() {
    if (state.status !== 'signed-in' || loggingOut) return;
    setLoggingOut(true); setLogoutError('');
    try {
      await authApi.logout(state.session);
      setState({ status: 'signed-out' });
      window.location.assign('/');
    } catch (error) {
      setLogoutError(error instanceof AuthApiError ? error.message : 'Oturum kapatılamadı.');
    } finally { setLoggingOut(false); }
  }

  return <AuthContext.Provider value={{ state, retry: () => setAttempt((value) => value + 1), logout, loggingOut, logoutError }}>{children}</AuthContext.Provider>;
}

export function useAuthSession() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthSessionProvider is required.');
  return value;
}
