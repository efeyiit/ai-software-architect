import type { ReactNode } from 'react';

export function SessionAction() {
  const https = typeof window !== 'undefined' && window.location.protocol === 'https:';
  return https
    ? <a className="subtle-button" href="/auth/github/login">Continue with GitHub</a>
    : <span className="secure-cookie-note">Live sign-in requires HTTPS because Ariadne sessions use Secure cookies.</span>;
}

export function FeatureNotice({ title, children, onRetry }: { title: string; children: ReactNode; onRetry?: () => void }) {
  return <div className="feature-notice" role="status"><span className="notice-mark" aria-hidden="true">i</span>
    <div><strong>{title}</strong><p>{children}</p>{onRetry && <button className="subtle-button" type="button" onClick={onRetry}>Try again</button>}</div>
  </div>;
}
