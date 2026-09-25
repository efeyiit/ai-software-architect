import { useEffect, useState } from 'react';
import type { LocalAnalysisResult } from '../../contracts/analysis';
import { FolderImport } from './FolderImport';
import { LocalReport } from './LocalReport';
import { LocalChat } from './LocalChat';
import { ThemeToggle } from '../../components/shell/ThemeToggle';
import { SourceText } from './SourceText';
import { loadReport, query, repositorySchema, request, sourceHref, startSession, type Job, type Limits, type LocalRepository } from './api';
import { LocalIcon, revealStyle } from './LocalIcon';
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
  return <section><div className="local-heading"><div><p className="local-eyebrow">{repo.source_kind === 'github' ? 'PUBLIC GITHUB REPOSITORY' : 'LOCAL SOURCE SNAPSHOT'}</p><h1>{repo.name}</h1><p className="local-muted">{repo.commit_sha ? `Git commit ${repo.commit_sha.slice(0, 12)}` : `Content ${repo.snapshot_id.slice(6, 18)}`} · Saved on this computer</p></div><button className="local-primary" disabled={busy || loading} aria-busy={busy || loading} onClick={async () => { setStarting(true); setError(''); try { setJob(await request('analyze', { repository_id: repo.repository_id, snapshot_id: repo.snapshot_id })); } catch (error) { setError(message(error)); } finally { setStarting(false); } }}>{busy ? 'Analyzing…' : report ? 'Analyze snapshot' : 'Run analysis'}</button></div>
    {job && <p role="status">Analysis: {job.status}{job.error_code ? ` · ${job.error_code}` : ''} {busy && <button onClick={async () => { try { await request(`jobs/${job.job_id}/cancel`, {}); } catch (error) { setError(message(error)); } }}>Cancel</button>}</p>}
    {error && <p className="local-error" role="alert">{error}</p>}
    <nav className="local-tabs" aria-label="Repository analysis views">{views.map(tab => <button key={tab} aria-current={view === tab ? 'page' : undefined} onClick={() => setView(tab)}>{tab}</button>)}</nav>
    <div className="local-report" key={view}><div className="local-section-heading"><h2>{view}</h2><span className="local-section-note">Saved analysis</span></div>{loading ? <p role="status">Loading saved sources…</p> : view === 'Files' ? <>
      {source !== null && path && <><h3>{path}</h3><SourceText content={source} line={Math.max(1, Number(params.get('line')) || 1)}/></>}
      <ul className="local-files">{files?.files.map(file => <li key={file}><a href={sourceHref(repo.repository_id, repo.snapshot_id, file)}>{file}</a></li>)}</ul>
      {Object.keys(files?.excluded ?? {}).length > 0 && <details><summary>Excluded files ({Object.keys(files!.excluded).length})</summary><ul>{Object.entries(files!.excluded).map(([file, reason]) => <li key={file}>{file} — {reason.replaceAll('_', ' ')}</li>)}</ul></details>}
      {repo.source_kind === 'local' && <FolderImport limits={limits} repositoryId={repo.repository_id} imported={refresh}/>}
    </> : view === 'AI chat' ? <LocalChat repo={repo}/> : report ? <LocalReport report={report} repo={repo} view={view}/> : <div className="local-empty"><h3>Ready to explore this codebase</h3><p>Run an analysis to see the structure, dependencies and findings. Each finding links back to the code.</p></div>}</div>
  </section>;
}

export function LocalWorkspace() {
  const [repos, setRepos] = useState<LocalRepository[]>([]);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const [filter, setFilter] = useState('');
  const [reducedMotion, setReducedMotion] = useState(() => {
    try { const saved = localStorage.getItem('ariadne:reduced-motion'); if (saved !== null) return saved === 'true'; } catch { /* A session preference still works. */ }
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });
  function toggleMotion() {
    const next = !reducedMotion;
    setReducedMotion(next);
    try { localStorage.setItem('ariadne:reduced-motion', String(next)); } catch { /* Keep the session preference. */ }
  }
  const [busy, setBusy] = useState(false);
  async function refresh() { setRepos(repositorySchema.array().parse(await request('repositories'))); }
  useEffect(() => { let active = true; startSession().then(async result => { if (!active) return; setLimits(result); await refresh(); }).catch(error => { if (active) setError(message(error)); }); return () => { active = false; }; }, []);
  const params = new URLSearchParams(window.location.search);
  const selected = repos.find(repo => repo.repository_id === params.get('repo'));
  const repo = selected && params.get('snapshot') ? { ...selected, snapshot_id: params.get('snapshot')!, commit_sha: params.get('snapshot')!.startsWith('github:') ? params.get('snapshot')!.slice(7) : null } : selected;
  const visibleRepos = repos.filter(item => item.name.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()));
  return <div className="local-shell" data-reduced-motion={reducedMotion}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="local-sidebar">
      <a href="/" className="local-brand"><img src="/brand/02-iplik.png" alt=""/><span>Ariadne<span className="local-brand-caption">Follow the thread.</span></span></a>
      <a className="local-workspace-link" href="/" aria-current={!repo ? 'page' : undefined}><LocalIcon name="grid"/><span>Workspace</span><span className="local-count">{repos.length}</span></a>
      <p className="local-nav-label">Repositories</p>
      <nav aria-label="Saved repositories">{repos.map(item => <a key={item.repository_id} href={`/?${new URLSearchParams({repo: item.repository_id})}`} aria-current={item.repository_id === repo?.repository_id ? 'page' : undefined}><LocalIcon name={item.source_kind === 'github' ? 'branch' : 'folder'}/><span>{item.name}<small>{item.source_kind === 'github' ? 'Public GitHub' : 'Local source'}</small></span></a>)}</nav>
      <div className="local-sidebar-note"><LocalIcon name="monitor"/><div>On your computer<p><span className="status-dot"/> No account required</p></div></div>
    </aside>
    <div className={`local-main${repo ? '' : ' local-home'}`}>
      <header className="local-topbar"><div className="local-breadcrumb"><a href="/">Workspace</a><span>/</span><strong>{repo?.name ?? 'Repositories'}</strong></div><div className="local-topbar-actions"><button className="local-motion-toggle" aria-label="Reduce motion" aria-pressed={reducedMotion} onClick={toggleMotion} title="Reduce motion"><LocalIcon name="spark"/><span>Reduce motion</span></button><ThemeToggle/></div></header>
      <main id="main-content" tabIndex={-1}>
        {error && <p className="local-error" role="alert">{error}</p>}
        {!limits ? <div className="local-loading" role="status"><span className="local-spinner"/>Opening your workspace…</div> : repo ? <RepositoryPanel key={`${repo.repository_id}:${repo.snapshot_id}`} repo={repo} limits={limits} refresh={() => { void refresh().catch(error => setError(message(error))); }}/> : <>
          <div className="local-hero">
            <div><h1>Your code,<br/><span>untangled.</span></h1><p>Open a project. See how it fits together.</p></div>
          </div>
          <div className="local-import-grid">
            <section className="local-import-section"><div className="local-import-title"><h2>Start with a GitHub link</h2><p>Any public repository. No sign-in needed.</p></div>
              <form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try { const imported = repositorySchema.parse(await request('github', { github_url: url })); window.location.assign(`/?${new URLSearchParams({repo: imported.repository_id})}`); } catch (error) { setError(message(error)); } finally { setBusy(false); } }}>
                <label className="local-sr-only" htmlFor="github-url">GitHub repository URL</label><div className="local-url-entry"><LocalIcon name="branch"/><input id="github-url" type="url" placeholder="https://github.com/owner/repository" required value={url} disabled={busy} aria-busy={busy} onChange={event => setUrl(event.target.value)}/>
                <button className="local-primary" disabled={busy} aria-busy={busy}>{busy ? <><span className="local-spinner"/>Importing…</> : <>Open repository<LocalIcon name="arrow"/></>}</button></div>
              </form>
            </section>
            <section className="local-import-section"><div className="local-import-title"><h2>Or open a folder</h2></div><FolderImport limits={limits} imported={() => { void refresh().catch(error => setError(message(error))); }}/></section>
          </div>
          <section className="local-library" aria-labelledby="repository-list-title">
            <div className="local-section-heading"><h2 id="repository-list-title">Your repositories <span className="local-count">{repos.length}</span></h2><label className="local-search"><LocalIcon name="search"/><span className="local-sr-only">Search repositories</span><input type="search" placeholder="Find a repository…" value={filter} onChange={event => setFilter(event.target.value)}/></label></div>
            {visibleRepos.length ? <div className="local-repo-grid">{visibleRepos.map((item, index) => <a className="local-repo-card" style={revealStyle(index)} href={`/?${new URLSearchParams({repo:item.repository_id})}`} key={item.repository_id}>
              <span className="local-repo-symbol"><LocalIcon name={item.source_kind === 'github' ? 'branch' : 'folder'}/></span><div className="local-repo-name"><h3>{item.name}</h3><span>{item.source_kind === 'github' ? 'Public GitHub repository' : 'Local source folder'}</span></div><code className="local-revision">{item.commit_sha ? item.commit_sha.slice(0, 7) : item.snapshot_id.slice(6, 13)}<span>{item.commit_sha ? 'commit' : 'snapshot'}</span></code><LocalIcon name="arrow"/>
            </a>)}</div> : <div className="local-empty"><LocalIcon name={filter ? 'search' : 'folder'}/><h3>{filter ? 'No matching repositories' : 'No projects yet'}</h3><p>{filter ? 'Try a different repository name.' : 'Import a GitHub repository or choose a source folder above.'}</p>{filter && <button className="local-secondary" onClick={() => setFilter('')}>Clear search</button>}</div>}
          </section>
        </>}
      </main>
      <footer className="local-footer"><span>Ariadne <span className="local-footer-divider">/</span> Explore your code</span><span>Projects are saved on this computer.</span></footer>
    </div>
  </div>;
}
