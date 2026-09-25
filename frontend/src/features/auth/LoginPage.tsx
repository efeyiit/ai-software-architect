import type { AuthState } from './AuthSession';
import { ThreadMark } from '../../components/shell/ThreadMark';
import { ThemeToggle } from '../../components/shell/ThemeToggle';
import './auth.css';

export function LoginPage({ state, retry, required = false }: { state: AuthState; retry: () => void; required?: boolean }) {
  const error = state.status === 'error' ? state.error : null;
  const configurationMissing = error?.kind === 'configuration';
  const serviceUnavailable = error && error.kind !== 'configuration';
  return <main className="login-page"><section className="login-card">
    <div className="login-card-header"><span className="brand"><span>Ariadne</span></span><ThemeToggle/></div>
    <div className="login-icon"><ThreadMark/></div>
    <p className="eyebrow">YOUR CODEBASE, IN CONTEXT</p>
    <h1>{configurationMissing ? 'GitHub sign-in is not configured' : required ? 'Sign in to continue' : 'Sign in to Ariadne'}</h1>
    <p className="login-description">{configurationMissing ? 'This deployment is missing the GitHub OAuth or database configuration required to create a secure session.' : required ? 'Your session is missing or expired. Sign in with GitHub to continue to your repositories.' : 'Connect your GitHub account to add a public repository and analyze its current source snapshot.'}</p>
    {state.status === 'loading' && <div className="login-status" role="status" aria-busy="true"><span className="loading-orbit"/>Checking your session…</div>}
    {state.status === 'signed-out' && <a className="github-button" href="/auth/github/login"><svg className="github-mark" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" stroke="none" d="M12 .9a11.1 11.1 0 0 0-3.51 21.63c.55.1.76-.24.76-.54v-2.1c-3.1.68-3.75-1.32-3.75-1.32-.5-1.3-1.24-1.65-1.24-1.65-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15 1 .1 1.68 1.93 3.7 1.45.1-.72.39-1.22.7-1.5-2.48-.28-5.1-1.24-5.12 5.52.4.34.76 1.02.76 2.06v3.05c0 .3.2.65.77.54A11.1 11.1 0 0 0 12 .9Z"/></svg>Continue with GitHub</a>}
    {configurationMissing && <div className="auth-configuration-notice" role="status"><strong>Configuration required</strong><p>GitHub OAuth credentials, an HTTPS callback, and the identity database must be configured by the service operator. No account is shown as connected.</p></div>}
    {serviceUnavailable && <div className="auth-configuration-notice" role="alert"><strong>Sign-in status could not be checked</strong><p>The authentication service returned an error. No session state was assumed.</p><button className="subtle-button" type="button" onClick={retry}>Retry session check</button></div>}
    {required && state.status === 'signed-out' && <p className="login-note">A valid server-side session is required to access this page.</p>}
  </section><p className="login-footer">A clearer view of the software you work on.</p></main>;
}
