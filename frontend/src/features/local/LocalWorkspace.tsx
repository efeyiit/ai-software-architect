import { useEffect, useState } from 'react';
import type { LocalAnalysisResult } from '../../contracts/analysis';
import { FolderImport } from './FolderImport';
import { LocalReport } from './LocalReport';
import { LocalChat } from './LocalChat';
import { ThemeToggle } from '../../components/shell/ThemeToggle';
import { SourceText } from './SourceText';
import { loadReport, query, repositorySchema, request, sourceHref, startSession, type Job, type Limits, type LocalRepository } from './api';
import './local.css';

const views = ['Overview', 'Files', 'Architecture', 'Dependencies', 'Findings', 'Security', 'Testing', 'Refactoring', 'Documentation', 'AI chat'];
const message = (error: unknown) => error instanceof Error ? error.message : 'The request failed.';

function RepositoryPanel({ repo, limits, refresh }: { repo: LocalRepository; limits: Limits; refresh: () => void }) {
  const params = new URLSearchParams(window.location.search);
  const path = params.get('path');
  const [view, setView] = useState(path ? 'Files' : 'Overview');
  const [files, setFiles] = useState<{files: string[]; excluded: Record<string, string>} | null>(null);
  const [report, setReport] = useState<LocalAnalysisResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([request(`files?${query(repo)}`, undefined, controller.signal), loadReport(repo, controller.signal),
      path ? request(`source?${query(repo)}&${new URLSearchParams({ path })}`, undefined, controller.signal) : Promise.resolve(null)])
      .then(([fileList, latest, selected]) => { setFiles(fileList); setReport(latest); setSource(selected?.content ?? null); setLoading(false); })
      .catch(error => { if (!controller.signal.aborted) { setError(message(error)); setLoading(false); } });
    return () => controller.abort();
  }, [repo.repository_id, repo.snapshot_id, path]);
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const next = await request(`jobs/${encodeURIComponent(job.job_id)}`, undefined, controller.signal) as Job;
        if (next.analysis_id) setReport(await loadReport(repo, controller.signal));
        setJob(next);
      } catch (error) { if (!controller.signal.aborted) setError(message(error)); }
    }, 600);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [job, repo.repository_id, repo.snapshot_id]);
  const busy = starting || Boolean(job && ['queued','running'].includes(job.status));
  return <section><div className="local-heading"><div><p className="local-eyebrow">{repo.source_kind === 'github' ? 'PUBLIC GITHUB REPOSITORY' : 'LOCAL SOURCE SNAPSHOT'}</p><h1>{repo.name}</h1><p className="local-muted">{repo.commit_sha ? `Git commit ${repo.commit_sha.slice(0, 12)}` : `Content ${repo.snapshot_id.slice(6, 18)}`} · Saved on this computer</p></div><button className="local-primary" disabled={busy || loading} onClick={async () => { setStarting(true); setError(''); try { setJob(await request('analyze', { repository_id: repo.repository_id, snapshot_id: repo.snapshot_id })); } catch (error) { setError(message(error)); } finally { setStarting(false); } }}>{busy ? 'Analyzing…' : report ? 'Analyze snapshot' : 'Run analysis'}</button></div>
    {job && <p role="status">Analysis: {job.status}{job.error_code ? ` · ${job.error_code}` : ''} {busy && <button onClick={async () => { try { await request(`jobs/${job.job_id}/cancel`, {}); } catch (error) { setError(message(error)); } }}>Cancel</button>}</p>}
    {error && <p className="local-error" role="alert">{error}</p>}
    <nav className="local-tabs" aria-label="Repository analysis views">{views.map(tab => <button key={tab} aria-current={view === tab ? 'page' : undefined} onClick={() => setView(tab)}>{tab}</button>)}</nav>
    <div className="local-report"><h2>{view}</h2>{loading ? <p role="status">Loading saved sources…</p> : view === 'Files' ? <>
      {source !== null && path && <><h3>{path}</h3><SourceText content={source} line={Math.max(1, Number(params.get('line')) || 1)}/></>}
      <ul className="local-files">{files?.files.map(file => <li key={file}><a href={sourceHref(repo.repository_id, repo.snapshot_id, file)}>{file}</a></li>)}</ul>
      {Object.keys(files?.excluded ?? {}).length > 0 && <details><summary>Excluded files ({Object.keys(files!.excluded).length})</summary><ul>{Object.entries(files!.excluded).map(([file, reason]) => <li key={file}>{file} — {reason.replaceAll('_', ' ')}</li>)}</ul></details>}
      {repo.source_kind === 'local' && <FolderImport limits={limits} repositoryId={repo.repository_id} imported={refresh}/>}
    </> : view === 'AI chat' ? <LocalChat repo={repo}/> : report ? <LocalReport report={report} repo={repo} view={view}/> : <div className="local-empty"><h3>Ready to explore this codebase</h3><p>Run analysis to build a source-linked report. No login or AI model is required for static analysis.</p></div>}</div>
  </section>;
}

export function LocalWorkspace() {
  const [repos, setRepos] = useState<LocalRepository[]>([]);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() { setRepos(repositorySchema.array().parse(await request('repositories'))); }
  useEffect(() => { let active = true; startSession().then(async result => { if (!active) return; setLimits(result); await refresh(); }).catch(error => { if (active) setError(message(error)); }); return () => { active = false; }; }, []);
  const params = new URLSearchParams(window.location.search);
  const selected = repos.find(repo => repo.repository_id === params.get('repo'));
  const repo = selected && params.get('snapshot') ? { ...selected, snapshot_id: params.get('snapshot')!, commit_sha: params.get('snapshot')!.startsWith('github:') ? params.get('snapshot')!.slice(7) : null } : selected;
  return <div className="local-shell"><a className="skip-link" href="#main-content">Skip to content</a><aside className="local-sidebar"><a href="/" className="local-brand"><img src="/brand/02-iplik.png" alt=""/>Ariadne</a><p className="local-eyebrow">YOUR WORKSPACE</p><a className="local-workspace-link" href="/">All repositories <span>{repos.length}</span></a><nav aria-label="Saved repositories">{repos.map(item => <a key={item.repository_id} href={`/?${new URLSearchParams({repo: item.repository_id})}`} aria-current={item.repository_id === repo?.repository_id ? 'page' : undefined}>{item.name}<small>{item.source_kind === 'github' ? 'GitHub' : 'Local folder'}</small></a>)}</nav><div className="local-sidebar-note"><span className="status-dot"/> Local workspace<p>No account required.</p></div></aside><div className="local-main"><header className="local-topbar"><span>Workspace / {repo?.name ?? 'Repositories'}</span><span className="local-badge">Local mode</span><ThemeToggle/></header><main id="main-content" tabIndex={-1}>
    {error && <p className="local-error" role="alert">{error}</p>}
    {!limits ? <p role="status">Opening your local workspace…</p> : repo ? <RepositoryPanel key={`${repo.repository_id}:${repo.snapshot_id}`} repo={repo} limits={limits} refresh={() => { void refresh().catch(error => setError(message(error))); }}/> : <>
      <div className="local-heading"><div><p className="local-eyebrow">FROM SOURCE TO UNDERSTANDING</p><h1>Your code, untangled.</h1><p className="local-muted">Explore architecture, dependencies and risks in a codebase.</p></div></div>
      <div className="local-import-grid"><section className="local-card"><span className="local-badge">01 · Public repository</span><h2>Start with a GitHub link</h2><p>Import a public repository at its current commit.</p><form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try { const imported = repositorySchema.parse(await request('github', { github_url: url })); window.location.assign(`/?${new URLSearchParams({repo: imported.repository_id})}`); } catch (error) { setError(message(error)); } finally { setBusy(false); } }}><label htmlFor="github-url">GitHub repository URL</label><input id="github-url" type="url" placeholder="https://github.com/owner/repository" required value={url} onChange={event => setUrl(event.target.value)}/><button className="local-primary" disabled={busy}>{busy ? 'Importing repository…' : 'Import from GitHub'}</button></form></section>
      <section className="local-card"><span className="local-badge">02 · Local or private code</span><h2>Open a folder</h2><p>Select source files from a project on this computer.</p><FolderImport limits={limits} imported={() => { void refresh().catch(error => setError(message(error))); }}/></section></div>
      <h2>Saved repositories <span className="local-muted">{repos.length}</span></h2>{repos.length ? <div className="local-repo-grid">{repos.map(item => <a className="local-card local-repo-card" href={`/?${new URLSearchParams({repo:item.repository_id})}`} key={item.repository_id}><span className="local-badge">{item.source_kind === 'github' ? 'Public GitHub' : 'Local folder'}</span><h3>{item.name}</h3><p>{item.commit_sha ? `Commit ${item.commit_sha.slice(0, 7)}` : `Snapshot ${item.snapshot_id.slice(6, 13)}`}</p><span>Explore repository →</span></a>)}</div> : <div className="local-empty"><h3>No repositories yet</h3><p>Import a public GitHub repository or choose a source folder to begin.</p></div>}
    </>}
    </main><footer className="local-footer">Ariadne <span>Understand the systems behind your code.</span></footer></div></div>;
}
