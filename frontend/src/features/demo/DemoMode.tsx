import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { localDemoApi } from './api';

type DemoMode = { requested: boolean; loading: boolean; verified: boolean; error: string };
const DemoModeContext = createContext<DemoMode>({ requested: false, loading: false, verified: false, error: '' });

export function DemoModeProvider({ children }: { children: ReactNode }) {
  const requested = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('demo') === 'fixture';
  const localLauncher = typeof window !== 'undefined' && ['127.0.0.1', 'localhost'].includes(window.location.hostname) && window.location.port === '8765';
  const shouldCheck = requested || localLauncher;
  const [state, setState] = useState<Pick<DemoMode, 'loading' | 'verified' | 'error'>>({ loading: shouldCheck, verified: false, error: '' });
  useEffect(() => {
    let active = true;
    if (!shouldCheck) { setState({ loading: false, verified: false, error: '' }); return () => { active = false; }; }
    setState({ loading: true, verified: false, error: '' });
    localDemoApi.getMeta().then((meta) => {
      if (active) setState({ loading: false, verified: meta.mode === 'local_demo' && meta.data_origin === 'bundled_synthetic', error: '' });
    }).catch((error: unknown) => {
      if (active) setState({ loading: false, verified: false, error: error instanceof Error ? error.message : 'Yerel demo doğrulanamadı.' });
    });
    return () => { active = false; };
  }, [shouldCheck]);
  return <DemoModeContext.Provider value={{ requested, ...state }}>{children}</DemoModeContext.Provider>;
}

export function useDemoMode() { return useContext(DemoModeContext); }
