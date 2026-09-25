import { useEffect, useState } from 'react';
import type { AnalysisResultData, RepositoryDiagrams, RepositoryInfo } from '../overview/api';
import { AriadneApi, ApiError } from '../overview/api';
import { FeatureNotice, SessionAction } from '../overview/SessionAction';
import { DependencyGraph } from '../dependencies/DependencyGraph';
import { MermaidPreview } from './MermaidPreview';
import { sourceHref } from './source-links';
import '../overview/overview.css';
import './architecture.css';

const api = new AriadneApi();
type View = 'architecture' | 'dependencies';
type Load = 'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error';

const architectureNames: Record<string, string> = {
  mvc: 'MVC', layered: 'Layered architecture', clean: 'Clean architecture', hexagonal: 'Hexagonal architecture',
  microservices: 'Microservices', modular_monolith: 'Modular monolith', event_driven: 'Event driven architecture',
};

function isControlledFixture() {
  return typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('demo') === 'fixture';
}

function statusMessage(error: unknown) {
  if (error instanceof ApiError && error.kind === 'unauthorized') return 'Your session is missing or expired. Sign in through GitHub to continue.';
  if (error instanceof ApiError && error.kind === 'unavailable') return 'The Ariadne API is unavailable. No sample report is shown in live mode.';
  if (error instanceof ApiError && error.kind === 'conflict') return 'The repository changed during this request. Reload to use its current snapshot.';
  return 'The architecture report could not be loaded.';
}

export function assertCurrentDiagramSnapshot(diagrams: RepositoryDiagrams, repositoryId: string, repositorySha: string, reportSha: string) {
  if (diagrams.snapshot.repository_id !== repositoryId || diagrams.snapshot.commit_sha !== repositorySha || diagrams.snapshot.commit_sha !== reportSha)
    throw new ApiError('conflict', 'Diagram source belongs to a different repository snapshot.');
}

function SourceLink({ repository, path, line }: { repository: RepositoryInfo; path: string; line: number }) {
  const href = sourceHref(repository, path, line);
  return href ? <a className="architecture-source-link" href={href} target="_blank" rel="noopener noreferrer">{path}:{line}</a> : <span className="architecture-source-link">{path}:{line}</span>;
}

function ArchitectureEvidence({ repository, items, label }: { repository: RepositoryInfo; items: { description: string; location: { path: string; start_line: number } }[]; label: string }) {
  if (!items.length) return <p className="architecture-muted">No {label.toLowerCase()} were returned.</p>;
  return <ul className="architecture-evidence">{items.map((item, index) => <li key={`${item.location.path}:${item.location.start_line}:${index}`}>
    <span>{item.description}</span><SourceLink repository={repository} path={item.location.path} line={item.location.start_line}/>
  </li>)}</ul>;
}

function Hypotheses({ analysis, repository }: { analysis: AnalysisResultData; repository: RepositoryInfo }) {
  const architecture = analysis.schema_version === 2 ? analysis.architecture : null;
  if (!architecture) return <FeatureNotice title="Architecture findings unavailable">This analysis has no architecture hypotheses. The screen does not infer a replacement report.</FeatureNotice>;
  if (!architecture.hypotheses.length) return <FeatureNotice title="No architecture evidence">The current report contains no architecture hypotheses.</FeatureNotice>;
  return <>
    <div className="architecture-summary" role="status"><strong>{architecture.summary === 'single' ? architectureNames[architecture.primary ?? ''] ?? 'One supported hypothesis' : architecture.summary === 'mixed' ? 'Mixed architectural signals' : 'Architecture remains unknown'}</strong>
      <span>{architecture.primary ? `Primary hypothesis: ${architectureNames[architecture.primary]}` : 'No single primary architecture was selected.'}</span></div>
    <div className="architecture-hypotheses">{architecture.hypotheses.map((hypothesis) => <article className="architecture-hypothesis" key={hypothesis.architecture}>
      <div className="architecture-hypothesis-heading"><div><h3>{architectureNames[hypothesis.architecture]}</h3><span className={`architecture-assessment assessment-${hypothesis.assessment}`}>{hypothesis.assessment}</span></div>
        <div className={`architecture-confidence confidence-${hypothesis.confidence}`}><span>Evidence signal · ordinal</span><strong>{hypothesis.confidence === 'high' ? 'Strong' : hypothesis.confidence === 'medium' ? 'Moderate' : 'Limited'}</strong></div></div>
      <p className="architecture-not-probability">This evidence level is an ordinal signal, not a probability.</p>
      <div className="architecture-evidence-columns"><section><h4>Supporting evidence</h4><ArchitectureEvidence repository={repository} items={hypothesis.reasons} label="Supporting evidence"/></section>
        <section><h4>Contradictions</h4><ArchitectureEvidence repository={repository} items={hypothesis.contradictions} label="Contradictions"/></section></div>
      {hypothesis.uncertainties.length > 0 && <div className="architecture-uncertainties"><h4>Uncertainties</h4><ul>{hypothesis.uncertainties.map((uncertainty, index) => <li key={index}>{uncertainty}</li>)}</ul></div>}
    </article>)}</div>
  </>;
}

function DiagramAvailability({ diagrams, load, error, onRetry }: { diagrams: RepositoryDiagrams | null; load: 'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error' | 'empty'; error: unknown; onRetry: () => void }) {
  const [view, setView] = useState<'class_diagram' | 'sequence_diagram' | 'component_diagram'>('component_diagram');
  const [format, setFormat] = useState<'mermaid' | 'plantuml'>('mermaid');
  const [output, setOutput] = useState<'preview' | 'source'>('preview');
  const labels = { class_diagram: 'Class', sequence_diagram: 'Sequence', component_diagram: 'Component' };
  const diagramSource = diagrams?.diagrams[format][view] ?? '';
  function downloadSource() {
    const blob = new Blob([diagramSource], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${view.replace('_diagram', '')}.${format === 'mermaid' ? 'mmd' : 'puml'}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const errorMessage = error instanceof ApiError && error.kind === 'unauthorized' ? 'Your session is missing or expired. Sign in to load diagrams.' :
    error instanceof ApiError && error.kind === 'unavailable' ? 'The diagrams API is currently unavailable.' :
      error instanceof ApiError && error.kind === 'conflict' ? 'The repository changed while loading diagrams. Reload this page for the current snapshot.' :
        'The diagram response could not be validated.';
  return <section className="architecture-diagrams" aria-labelledby="diagrams-title">
    <div className="architecture-section-heading"><div><span className="section-kicker">T18 DIAGRAM OUTPUT</span><h2 id="diagrams-title">Code diagrams</h2></div><span className={`diagram-unavailable${diagrams ? ' diagram-ready' : ''}`}>{diagrams ? `Source · ${diagrams.status}` : 'T18 API'}</span></div>
    {load === 'loading' && <div className="inline-loading" aria-busy="true"><span className="loading-orbit"/>Loading current snapshot diagram output…</div>}
    {load === 'empty' && <p>This analysis has no dependency graph for T18 to render.</p>}
    {(load === 'unauthorized' || load === 'unavailable' || load === 'error') && <div className="diagram-error" role="alert"><p>{errorMessage}{load === 'unauthorized' && <> <SessionAction/></>}</p>{load !== 'unauthorized' && <button type="button" className="subtle-button" onClick={onRetry}>Retry diagrams</button>}</div>}
    {diagrams && <>
      <p>Mermaid diagrams render locally in a restricted sandbox. PlantUML stays available as source for use in your local tools; neither format is sent to a remote renderer.</p>
      <div className="diagram-options" aria-label="Diagram options">
        <fieldset><legend>View</legend>{(Object.keys(labels) as (keyof typeof labels)[]).map((item) => <label key={item}><input type="radio" name="diagram-view" checked={view === item} onChange={() => setView(item)}/> {labels[item]}</label>)}</fieldset>
        <fieldset><legend>Format</legend>{(['mermaid', 'plantuml'] as const).map((item) => <label key={item}><input type="radio" name="diagram-format" checked={format === item} onChange={() => { setFormat(item); setOutput(item === 'mermaid' ? 'preview' : 'source'); }}/> {item === 'mermaid' ? 'Mermaid' : 'PlantUML'}</label>)}</fieldset>
      </div>
      {format === 'mermaid' ? <>
        <div className="diagram-output-tabs" role="group" aria-label="Mermaid output mode"><button type="button" aria-pressed={output === 'preview'} onClick={() => setOutput('preview')}>Preview</button><button type="button" aria-pressed={output === 'source'} onClick={() => setOutput('source')}>Source</button></div>
        {output === 'preview' ? <MermaidPreview source={diagramSource} kind={view.replace('_diagram', '') as 'class' | 'sequence' | 'component'} title={`Mermaid ${labels[view].toLowerCase()} diagram preview`}/> : <pre className="diagram-source" aria-label={`${labels[view]} Mermaid source`}><code>{diagramSource}</code></pre>}
        <button type="button" className="subtle-button diagram-download" onClick={downloadSource}>Download Mermaid source</button>
      </> : <>
        <p className="diagram-format-note">PlantUML is provided as source for local use. It is not sent to a remote renderer.</p>
        <pre className="diagram-source" aria-label={`${labels[view]} PlantUML source`}><code>{diagramSource}</code></pre>
        <button type="button" className="subtle-button diagram-download" onClick={downloadSource}>Download PlantUML source</button>
      </>}
      {diagrams.status === 'partial' && <p className="architecture-partial"><strong>Partial diagram bundle.</strong> The T18 API reports a partial analysis.</p>}
    </>}
  </section>;
}

export function ArchitecturePage({ repositoryId, view = 'architecture' }: { repositoryId: string; view?: View }) {
  const [load, setLoad] = useState<Load>('loading');
  const [repository, setRepository] = useState<RepositoryInfo | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResultData | null>(null);
  const [diagrams, setDiagrams] = useState<RepositoryDiagrams | null>(null);
  const [diagramLoad, setDiagramLoad] = useState<'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error' | 'empty'>('loading');
  const [diagramError, setDiagramError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoad('loading');
    setDiagramLoad('loading'); setDiagrams(null); setDiagramError(null);
    Promise.all([api.getRepository(repositoryId), api.getLatestAnalysis(repositoryId)]).then(([repo, result]) => {
      if (!active) return;
      if (result && result.snapshot.repository_id !== repositoryId) throw new ApiError('conflict', 'Report belongs to a different repository.');
      if (result && result.snapshot.commit_sha !== repo.commit_sha) throw new ApiError('conflict', 'Report belongs to a different commit.');
      setRepository(repo); setAnalysis(result); setError(null); setLoad('ready');
      if (!result || result.schema_version !== 2 || !result.dependencies) { setDiagramLoad('empty'); return; }
      return api.getDiagrams(repositoryId).then((bundle) => {
        if (!active) return;
        assertCurrentDiagramSnapshot(bundle, repositoryId, repo.commit_sha, result.snapshot.commit_sha);
        setDiagrams(bundle); setDiagramError(null); setDiagramLoad('ready');
      }).catch((reason: unknown) => {
        if (!active) return;
        setDiagramError(reason); setDiagramLoad(reason instanceof ApiError && reason.kind === 'unauthorized' ? 'unauthorized' :
          reason instanceof ApiError && reason.kind === 'unavailable' ? 'unavailable' : 'error');
      });
    }).catch((reason: unknown) => {
      if (!active) return;
      setError(reason); setLoad(reason instanceof ApiError && reason.kind === 'unauthorized' ? 'unauthorized' :
        reason instanceof ApiError && reason.kind === 'unavailable' ? 'unavailable' : 'error');
    });
    return () => { active = false; };
  }, [repositoryId, attempt]);

  async function retryDiagrams() {
    if (!repository || !analysis || analysis.schema_version !== 2 || !analysis.dependencies) return;
    setDiagramLoad('loading'); setDiagramError(null);
    try {
      const bundle = await api.getDiagrams(repositoryId);
      assertCurrentDiagramSnapshot(bundle, repositoryId, repository.commit_sha, analysis.snapshot.commit_sha);
      setDiagrams(bundle); setDiagramLoad('ready');
    } catch (reason) {
      setDiagramError(reason); setDiagramLoad(reason instanceof ApiError && reason.kind === 'unauthorized' ? 'unauthorized' : reason instanceof ApiError && reason.kind === 'unavailable' ? 'unavailable' : 'error');
    }
  }

  if (load === 'loading') return <section className="feature-loading" aria-busy="true" aria-live="polite"><span className="loading-orbit"/>{view === 'architecture' ? 'Loading architecture report…' : 'Loading dependency report…'}</section>;
  if (load !== 'ready' || !repository) return <section className="feature-page architecture-page"><FeatureNotice title={load === 'unauthorized' ? 'Sign in required' : load === 'unavailable' ? 'Architecture API unavailable' : 'Could not load architecture'} onRetry={load === 'unauthorized' ? undefined : () => setAttempt((value) => value + 1)}>{statusMessage(error)}{load === 'unauthorized' && <> <SessionAction/></>}</FeatureNotice></section>;
  if (!analysis) return <section className="feature-page architecture-page"><div className="feature-heading"><div><p className="eyebrow">REPOSITORY ARCHITECTURE</p><h1>{repository.name}</h1><p className="feature-subtitle">No analysis exists for the current snapshot.</p></div></div><FeatureNotice title="No analysis for this snapshot">Run an analysis from the repository overview to see architecture and dependency results.</FeatureNotice><a className="subtle-button architecture-overview-link" href={`/repository/${encodeURIComponent(repositoryId)}`}>Go to repository overview</a></section>;
  const currentViewData = view === 'architecture' ? analysis.schema_version === 2 ? analysis.architecture : null : analysis.schema_version === 2 ? analysis.dependencies : null;
  return <section className="feature-page architecture-page">
    {import.meta.env.DEV && isControlledFixture() && <div className="demo-banner" role="note"><strong>TEST / CONTROLLED API FIXTURE</strong><span>Browser-intercepted response. This is not live repository or authentication evidence.</span></div>}
    <div className="feature-heading"><div><p className="eyebrow">REPOSITORY {view === 'architecture' ? 'ARCHITECTURE' : 'DEPENDENCIES'}</p><h1>{view === 'architecture' ? 'Architecture map' : 'Dependency graph'}</h1><p className="feature-subtitle">{repository.name} <span aria-hidden="true">·</span> <code>{analysis.snapshot.commit_sha.slice(0, 7)}</code></p></div>
      <span className={`analysis-badge status-${analysis.status}`}><i aria-hidden="true"/>{analysis.status === 'partial' ? 'Partial results' : analysis.status}</span></div>
    {analysis.status === 'partial' && <div className="architecture-partial" role="status"><strong>Partial report.</strong> Some analysis roles failed or timed out; review the report errors before relying on this view.</div>}
    {analysis.errors.length > 0 && <details className="architecture-report-errors"><summary>Report errors ({analysis.errors.length})</summary><ul>{analysis.errors.map((item, index) => <li key={`${item.code}:${index}`}><strong>{item.code}</strong> {item.message}</li>)}</ul></details>}
    {!currentViewData && <FeatureNotice title={view === 'architecture' ? 'Architecture data unavailable' : 'Dependency data unavailable'}>The current analysis does not contain this section. No synthetic data is substituted.</FeatureNotice>}
    {analysis.schema_version === 2 && view === 'architecture' && <Hypotheses analysis={analysis} repository={repository}/>}
    {analysis.schema_version === 2 && view === 'dependencies' && analysis.dependencies && <DependencyGraph graph={analysis.dependencies} repository={repository}/>}
    <DiagramAvailability diagrams={diagrams} load={diagramLoad} error={diagramError} onRetry={() => { void retryDiagrams(); }}/>
  </section>;
}
