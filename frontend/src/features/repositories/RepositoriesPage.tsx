import { useEffect, useState, type FormEvent } from 'react';
import { FeatureNotice } from '../overview/SessionAction';
import type { Session } from '../auth/api';
import { RepositoryApiError, repositoryApi, type RepositoryEntry } from './api';
import './repositories.css';

function listMessage(error: unknown) {
  if (!(error instanceof RepositoryApiError)) return 'Repository list could not be loaded.';
  if (error.code === 'configuration_unavailable' || error.code === 'database_unavailable') return 'Repository service configuration is incomplete.';
  if (error.code === 'login_required' || error.status === 401) return 'Your session expired. Sign in again to see your repositories.';
  if (error.code === 'service_unavailable' || error.status === 503) return 'Repository service is unavailable. Try again later.';
  if (error.code === 'http_404' || error.code === 'not_found') return 'The repository list endpoint is not available. You can still connect a repository below and open it from the successful result.';
  return 'Repository list response could not be verified.';
}

function createMessage(error: unknown) {
  if (!(error instanceof RepositoryApiError)) return 'The repository could not be connected.';
  if (error.code === 'csrf_required') return 'Your session security token is out of date. Refresh your session and try again.';
  if (error.code === 'repository_exists' || error.status === 409) return 'This repository is already connected to your account.';
  if (error.code.includes('not_found')) return 'GitHub could not find that public repository. Check the URL and access.';
  if (error.code.includes('invalid') || error.status === 422) return 'Use a valid GitHub repository URL, for example https://github.com/owner/repository.';
  if (error.code.includes('unavailable') || error.status === 503) return 'GitHub or the Ariadne repository service is currently unavailable.';
  if (error.status === 401) return 'Your sign-in session expired. Sign in again.';
  return 'The repository was not connected. No success was recorded.';
}

export function RepositoriesPage({ session }: { session: Session }) {
  const [repositories, setRepositories] = useState<RepositoryEntry[]>([]);
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [listError, setListError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const [url, setUrl] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [created, setCreated] = useState<RepositoryEntry | null>(null);

  useEffect(() => {
    let active = true;
    setListState('loading');
    repositoryApi.list().then((items) => {
      if (active) { setRepositories(items); setListState('ready'); setListError(null); }
    }).catch((error: unknown) => { if (active) { setListError(error); setListState('error'); } });
    return () => { active = false; };
  }, [attempt]);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = url.trim();
    let parsed: URL;
    try { parsed = new URL(value); } catch { setCreateError('Enter a valid public GitHub repository URL.'); return; }
    const parts = parsed.pathname.replace(/\/$/, '').split('/').filter(Boolean);
    if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || parts.length !== 2 || !parts.every((part) => !part.includes('..'))) {
      setCreateError('Enter a public GitHub URL in the format https://github.com/owner/repository.'); return;
    }
    setCreating(true); setCreateError(''); setCreated(null);
    try {
      const result = await repositoryApi.create(value, session.csrf_token);
      setCreated(result);
      setRepositories((current) => current.some((repo) => repo.id === result.id) ? current : [result, ...current]);
      setUrl('');
    } catch (error) { setCreateError(createMessage(error)); }
    finally { setCreating(false); }
  }

  return <section className="repositories-page">
    <header className="page-heading"><p className="eyebrow">YOUR WORKSPACE</p><h1>Your repositories</h1><p className="page-description">Connect a public GitHub repository, then run an analysis on its current commit.</p></header>
    <div className="repository-connect-card"><div><span className="section-kicker">ADD A REPOSITORY</span><h2>Connect a public GitHub repository</h2><p>Only the public repository URL is needed. Ariadne reads the current default-branch snapshot and does not run repository code.</p></div>
      <form onSubmit={(event) => void connect(event)}><label htmlFor="repository-url">GitHub repository URL</label><div className="repository-url-row"><input id="repository-url" type="url" inputMode="url" autoComplete="url" maxLength={300} required value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/owner/repository" disabled={creating}/><button className="primary-button" type="submit" disabled={creating || !url.trim()}>{creating ? <><span className="button-spinner"/> Connecting…</> : 'Connect repository'}</button></div><p className="repository-form-note">Public repositories only in this flow. Private repository access is a separate, explicit authorization.</p>{createError && <p className="repository-form-error" role="alert">{createError}</p>}{created && <div className="repository-created" role="status"><strong>Repository connected.</strong><span>{created.name} · <code>{created.commit_sha.slice(0, 7)}</code></span><a href={`/repository/${encodeURIComponent(created.id)}`}>Open repository and run analysis <span aria-hidden="true">→</span></a></div>}</form>
    </div>
    <section className="repository-list-section" aria-labelledby="repository-list-title"><div className="repository-list-heading"><div><span className="section-kicker">CONNECTED TO YOUR ACCOUNT</span><h2 id="repository-list-title">Repositories</h2></div>{listState === 'ready' && <span className="count-pill">{repositories.length} connected</span>}</div>
      {listState === 'loading' && <div className="inline-loading" aria-busy="true"><span className="loading-orbit"/>Loading your repositories…</div>}
      {listState === 'error' && <FeatureNotice title="Repository list unavailable" onRetry={() => setAttempt((value) => value + 1)}>{listMessage(listError)}</FeatureNotice>}
      {listState === 'ready' && repositories.length === 0 && <div className="repository-empty"><strong>No repositories connected yet</strong><p>Connect one above. It will appear here after the API confirms it.</p></div>}
      {listState === 'ready' && repositories.length > 0 && <ul className="repository-list">{repositories.map((repository) => <li key={repository.id}><div><strong>{repository.name}</strong><a href={repository.github_url} target="_blank" rel="noopener noreferrer">{repository.github_url}</a><code>{repository.commit_sha.slice(0, 7)}</code></div><a className="subtle-button" href={`/repository/${encodeURIComponent(repository.id)}`}>Open repository <span aria-hidden="true">→</span></a></li>)}</ul>}
    </section>
  </section>;
}
