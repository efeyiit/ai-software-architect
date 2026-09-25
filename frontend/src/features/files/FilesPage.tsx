import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { AriadneApi, ApiError, type FileSummary, type RepositoryFile } from '../overview/api';
import { FeatureNotice, SessionAction } from '../overview/SessionAction';
import { useDemoMode } from '../demo/DemoMode';
import '../overview/overview.css';
import './files.css';

const api = new AriadneApi();

type FileTreeNode = { name: string; path: string; file?: RepositoryFile; children: Map<string, FileTreeNode> };

function makeTree(files: RepositoryFile[]) {
  const root: FileTreeNode = { name: '', path: '', children: new Map() };
  for (const file of files) {
    const parts = file.path.split('/');
    let current = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join('/');
      let child = current.children.get(part);
      if (!child) {
        child = { name: part, path, children: new Map() };
        current.children.set(part, child);
      }
      if (index === parts.length - 1) child.file = file;
      current = child;
    });
  }
  return root;
}

function FileTree({ node, selected, onSelect, level = 0 }: { node: FileTreeNode; selected: string | null; onSelect: (path: string) => void; level?: number }) {
  const children = [...node.children.values()].sort((a, b) => {
    if (Boolean(a.file) !== Boolean(b.file)) return a.file ? 1 : -1;
    return a.name.localeCompare(b.name);
  });
  return <ul className="file-tree-list">{children.map((child) => child.file ? <li key={child.path}>
    <button className={`file-tree-item${selected === child.path ? ' is-selected' : ''}${child.file.included ? '' : ' is-excluded'}`}
      type="button" aria-pressed={selected === child.path} disabled={!child.file.included} title={child.file.included ? undefined : `Excluded from analysis: ${child.file.exclusion_reason ?? 'unsupported file type'}`} onClick={() => onSelect(child.path)} style={{ '--tree-level': level } as CSSProperties}>
      <span className="file-kind-icon" aria-hidden="true">{child.file.included ? '◇' : '·'}</span><span className="file-name">{child.name}</span>
      {child.file.language && <span className="file-language">{child.file.language}</span>}{!child.file.included && <span className="excluded-tag">Excluded</span>}
    </button>
  </li> : <li className="file-tree-folder" key={child.path}><div className="folder-name" style={{ '--tree-level': level } as CSSProperties}><span aria-hidden="true">⌄</span>{child.name}</div>
    <FileTree node={child} selected={selected} onSelect={onSelect} level={level + 1}/></li>)}</ul>;
}

function Citation({ path, line, quote }: { path: string; line: number; quote: string | null }) {
  return <li><span className="citation-location">{path}:{line}</span>{quote && <q>{quote}</q>}</li>;
}

export function FilesPage({ repositoryId }: { repositoryId: string }) {
  const demoMode = useDemoMode();
  const [files, setFiles] = useState<RepositoryFile[]>([]);
  const [snapshotSha, setSnapshotSha] = useState<string | null>(null);
  const [load, setLoad] = useState<'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error'>('loading');
  const [loadError, setLoadError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [summary, setSummary] = useState<FileSummary | null>(null);
  const [summaryState, setSummaryState] = useState<'idle' | 'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error'>('idle');
  const [summaryError, setSummaryError] = useState<unknown>(null);
  const [summaryAttempt, setSummaryAttempt] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const tree = useMemo(() => makeTree(files), [files]);

  useEffect(() => {
    let active = true;
    setLoad('loading');
    setSelected(null);
    setSummary(null);
    setSummaryState('idle');
    if (demoMode.loading) return () => { active = false; };
    if (demoMode.verified) {
      import('../overview/demo-fixture').then(({ demoFiles, demoSnapshot }) => {
        if (!active) return;
        setFiles(demoFiles);
        setSnapshotSha(demoSnapshot.commit_sha);
        setLoad('ready');
      });
      return () => { active = false; };
    }
    Promise.all([api.getRepository(repositoryId), api.getFiles(repositoryId)]).then(([repository, response]) => {
      if (!active) return;
      if (response.snapshot.repository_id !== repositoryId || response.snapshot.commit_sha !== repository.commit_sha) {
        throw new ApiError('conflict', 'Repository tree and metadata refer to different snapshots.');
      }
      setFiles(response.files);
      setSnapshotSha(response.snapshot.commit_sha);
      setLoad('ready');
      setLoadError(null);
    }).catch((error: unknown) => {
      if (!active) return;
      setLoadError(error);
      setLoad(error instanceof ApiError && error.kind === 'unauthorized' ? 'unauthorized' :
        error instanceof ApiError && error.kind === 'unavailable' ? 'unavailable' : 'error');
    });
    return () => { active = false; };
  }, [repositoryId, attempt, demoMode.loading, demoMode.verified]);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    setSummaryState('loading');
    setSummary(null);
    setSummaryError(null);
    if (demoMode.loading) return () => { active = false; };
    if (demoMode.verified) {
      import('../overview/demo-fixture').then(({ demoSummary }) => {
        if (!active) return;
        setSummary(demoSummary);
        setSummaryState('ready');
      });
      return () => { active = false; };
    }
    api.getFileSummary(repositoryId, selected).then((result) => {
      if (!active) return;
      if (result.snapshot.repository_id !== repositoryId || result.snapshot.commit_sha !== snapshotSha || result.path !== selected) {
        throw new ApiError('conflict', 'File summary refers to a different file or repository snapshot.');
      }
      setSummary(result);
      setSummaryState('ready');
    }).catch((error: unknown) => {
      if (!active) return;
      setSummaryError(error);
      setSummaryState(error instanceof ApiError && error.kind === 'unauthorized' ? 'unauthorized' :
        error instanceof ApiError && (error.kind === 'unavailable' || error.kind === 'not_found') ? 'unavailable' : 'error');
    });
    return () => { active = false; };
  }, [repositoryId, selected, snapshotSha, summaryAttempt, demoMode.loading, demoMode.verified]);

  const included = files.filter((file) => file.included).length;
  const treeErrorMessage = loadError instanceof ApiError && loadError.kind === 'unauthorized'
    ? 'Your session is missing or expired. Sign in through GitHub to view this repository.'
    : loadError instanceof ApiError && loadError.kind === 'unavailable'
      ? 'The repository file-tree API is unavailable. No sample tree is shown in live mode.'
      : 'The file tree could not be loaded for the current repository snapshot.';

  return <section className="feature-page files-page">
    {demoMode.verified && <div className="demo-banner" role="note"><strong>LOCAL DEMO FIXTURE</strong><span>Synthetic file tree and summary. No real repository API response.</span></div>}
    <div className="feature-heading"><div><p className="eyebrow">REPOSITORY FILES</p><h1>Explore the source tree</h1><p className="feature-subtitle">Select an included source file to view its source-linked summary.</p></div>{load === 'ready' && <span className="source-chip">{included} included files · <code>{snapshotSha?.slice(0, 7)}</code></span>}</div>

    {load === 'loading' && <div className="feature-loading" aria-busy="true" aria-live="polite"><span className="loading-orbit"/>Loading repository file tree…</div>}
    {(load === 'unauthorized' || load === 'unavailable' || load === 'error') && <FeatureNotice title={load === 'unauthorized' ? 'Sign in required' : load === 'unavailable' ? 'File tree unavailable' : 'Could not load files'} onRetry={load === 'unauthorized' ? undefined : () => setAttempt((count) => count + 1)}>{treeErrorMessage}{load === 'unauthorized' && <> <SessionAction/></>}</FeatureNotice>}
    {load === 'ready' && files.length === 0 && <FeatureNotice title="No files in this snapshot">The current repository snapshot contains no files to display.</FeatureNotice>}
    {load === 'ready' && files.length > 0 && <div className="file-workspace">
      <section className="file-browser-card" aria-labelledby="tree-title"><div className="file-card-heading"><div><span className="section-kicker">SNAPSHOT TREE</span><h2 id="tree-title">Files</h2></div><span>{files.length}</span></div>
        <nav className="file-tree" aria-label="Repository file tree"><FileTree node={tree} selected={selected} onSelect={setSelected}/></nav>
      </section>
      <section className="file-summary-card" aria-labelledby="summary-title"><div className="file-card-heading"><div><span className="section-kicker">FILE EXPLANATION</span><h2 id="summary-title">{selected ? selected.split('/').at(-1) : 'Choose a file'}</h2></div>{selected && <span className="summary-status">{summary?.ai_status === 'unavailable' ? 'Deterministic only' : 'Source linked'}</span>}</div>
        {!selected && <div className="summary-placeholder"><div className="summary-placeholder-icon" aria-hidden="true">↖</div><h3>Select an included file</h3><p>Its summary and structural facts will appear here, with source paths and line references.</p></div>}
        {selected && summaryState === 'loading' && <div className="inline-loading" aria-busy="true"><span className="loading-orbit"/>Verifying the selected file and summary…</div>}
        {selected && summaryState === 'unauthorized' && <FeatureNotice title="Sign in required">Your session is missing or expired. <SessionAction/></FeatureNotice>}
        {selected && summaryState === 'unavailable' && <FeatureNotice title="Summary unavailable">{summaryError instanceof ApiError && summaryError.kind === 'unavailable' ? 'The summary service is currently unavailable.' : 'A source-grounded summary is not available for this file.'}<button className="subtle-button" type="button" onClick={() => setSummaryAttempt((count) => count + 1)}>Retry summary</button></FeatureNotice>}
        {selected && summaryState === 'error' && <FeatureNotice title="Could not load the file summary">{summaryError instanceof ApiError && summaryError.kind === 'conflict' ? 'The repository snapshot changed. Reload this page before selecting a file.' : 'The summary request failed.'}<button className="subtle-button" type="button" onClick={() => setSummaryAttempt((count) => count + 1)}>Retry summary</button></FeatureNotice>}
        {summary && summaryState === 'ready' && <div className="file-summary-content">
          {demoMode.verified && <span className="demo-content-tag">Fixture data</span>}
          <p className="responsibility-copy">{summary.responsibility}</p>
          <div className="uncertainty-note"><span aria-hidden="true">i</span>{summary.uncertainties.join(' ')}</div>
          <div className="summary-facts"><h3>Structural facts</h3>{summary.structural_facts.length === 0 ? <p className="muted-copy">No structural facts were produced by the parser.</p> : <ul>{summary.structural_facts.map((claim, index) => <li key={`${claim.text}-${index}`}><p>{claim.text}</p><ul className="citation-list">{claim.citations.map((citation, citationIndex) => <Citation key={`${citation.location.path}-${citation.location.start_line}-${citationIndex}`} path={citation.location.path} line={citation.location.start_line} quote={citation.quote}/>)}</ul></li>)}</ul>}</div>
          {summary.ai_claims.length > 0 && <div className="summary-facts"><h3>AI claims with validated citations</h3><ul>{summary.ai_claims.map((claim, index) => <li key={`${claim.text}-${index}`}><p>{claim.text}</p><ul className="citation-list">{claim.citations.map((citation, citationIndex) => <Citation key={`${citation.location.path}-${citation.location.start_line}-${citationIndex}`} path={citation.location.path} line={citation.location.start_line} quote={citation.quote}/>)}</ul></li>)}</ul></div>}
          {summary.responsibility_citations.length > 0 && <div className="summary-facts"><h3>Responsibility evidence</h3><ul className="citation-list">{summary.responsibility_citations.map((citation, index) => <Citation key={`${citation.location.path}-${citation.location.start_line}-${index}`} path={citation.location.path} line={citation.location.start_line} quote={citation.quote}/>)}</ul></div>}
          <p className="source-boundary">Source content is not exposed. Summaries are bound to commit <code>{summary.snapshot.commit_sha.slice(0, 7)}</code>.</p>
        </div>}
      </section>
    </div>}
  </section>;
}
