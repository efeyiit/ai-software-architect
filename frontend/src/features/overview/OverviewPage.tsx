import { useEffect, useRef, useState } from 'react';
import { AriadneApi, ApiError, type AnalysisResultData, type RepositoryInfo, type RepositoryFiles } from './api';
import { FeatureNotice, SessionAction } from './SessionAction';
import { useDemoMode } from '../demo/DemoMode';
import './overview.css';

const api = new AriadneApi();

type ViewState = 'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error';
type InventoryState = 'loading' | 'ready' | 'unauthorized' | 'unavailable' | 'error';
type ReportState = 'loading' | 'ready' | 'empty' | 'unauthorized' | 'unavailable' | 'error' | 'queued' | 'running';

export function assertAnalysisSnapshot(analysis: AnalysisResultData | null, repositoryId: string, commitSha: string): AnalysisResultData | null {
  if (analysis && (analysis.snapshot.repository_id !== repositoryId || analysis.snapshot.commit_sha !== commitSha)) {
    throw new ApiError('conflict', 'Analysis belongs to a different repository snapshot.');
  }
  return analysis;
}

function messageFor(error: unknown) {
  if (!(error instanceof ApiError)) return 'Something went wrong while loading this repository.';
  if (error.kind === 'unauthorized') return 'Your session is missing or expired. Sign in through GitHub to continue.';
  if (error.kind === 'unavailable') return 'The Ariadne API or this capability is currently unavailable.';
  if (error.kind === 'conflict') return 'The repository changed during this request. Reload to use its current snapshot.';
  return 'Repository data could not be loaded.';
}

function statusLabel(status: AnalysisResultData['status']) {
  return status === 'succeeded' ? 'Complete' : status === 'partial' ? 'Partial results' :
    status === 'failed' ? 'Failed' : status === 'cancelled' ? 'Cancelled' : status === 'pending' ? 'Queued' : 'Running';
}

function Metric({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <article className="overview-metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

export function OverviewPage({ repositoryId }: { repositoryId: string }) {
  const demoMode = useDemoMode();
  const [view, setView] = useState<ViewState>('loading');
  const [repository, setRepository] = useState<RepositoryInfo | null>(null);
  const [tree, setTree] = useState<RepositoryFiles | null>(null);
  const [inventory, setInventory] = useState<InventoryState>('loading');
  const [analysis, setAnalysis] = useState<AnalysisResultData | null>(null);
  const [report, setReport] = useState<ReportState>('loading');
  const [reportError, setReportError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const requestVersion = useRef(0);

  useEffect(() => {
    let active = true;
    requestVersion.current += 1;
    setAnalysis(null);
    setRepository(null);
    setBusy(false);
    setView('loading');
    setInventory('loading');
    setReport('loading');
    if (demoMode.loading) return () => { active = false; };
    if (demoMode.verified) {
      import('./demo-fixture').then(({ demoAnalysis, demoFiles, demoRepository, demoSnapshot }) => {
        if (!active) return;
        setRepository(demoRepository);
        setTree({ snapshot: demoSnapshot, files: demoFiles });
        setInventory('ready');
        setAnalysis(demoAnalysis);
        setView('ready');
        setReport('ready');
      });
      return () => { active = false; };
    }
    Promise.allSettled([api.getRepository(repositoryId), api.getFiles(repositoryId), api.getLatestAnalysis(repositoryId)]).then(([repoResult, filesResult, analysisResult]) => {
      if (!active) return;
      if (repoResult.status === 'rejected') {
        setRepository(null);
        setView(repoResult.reason instanceof ApiError && repoResult.reason.kind === 'unauthorized' ? 'unauthorized' :
          repoResult.reason instanceof ApiError && repoResult.reason.kind === 'unavailable' ? 'unavailable' : 'error');
        return;
      }
      if (repoResult.value.id !== repositoryId) {
        setRepository(null);
        setView('error');
        setAnalysis(null);
        setReportError(new ApiError('conflict', 'Repository response belongs to a different repository.'));
        setReport('error');
        return;
      }
      setRepository(repoResult.value);
      if (filesResult.status === 'fulfilled' && filesResult.value.snapshot.commit_sha === repoResult.value.commit_sha) {
        setTree(filesResult.value);
        setInventory('ready');
      } else {
        setTree(null);
        const error = filesResult.status === 'rejected' ? filesResult.reason : new ApiError('conflict', 'snapshot mismatch');
        setInventory(error instanceof ApiError && error.kind === 'unauthorized' ? 'unauthorized' :
          error instanceof ApiError && error.kind === 'unavailable' ? 'unavailable' : 'error');
      }
      setView('ready');
      if (analysisResult.status === 'fulfilled') {
        try {
          const current = assertAnalysisSnapshot(analysisResult.value, repositoryId, repoResult.value.commit_sha);
          setAnalysis(current);
          setReport(current ? 'ready' : 'empty');
          setReportError(null);
        } catch (error) {
          setAnalysis(null);
          setReportError(error);
          setReport('error');
        }
      } else {
        setReportError(analysisResult.reason);
        setReport(analysisResult.reason instanceof ApiError && analysisResult.reason.kind === 'unauthorized' ? 'unauthorized' :
          analysisResult.reason instanceof ApiError && analysisResult.reason.kind === 'unavailable' ? 'unavailable' : 'error');
      }
    });
    return () => { active = false; };
  }, [repositoryId, attempt, demoMode.loading, demoMode.verified]);

  async function runAnalysis() {
    if (demoMode.verified) return;
    const expectedRepository = repository;
    if (!expectedRepository || expectedRepository.id !== repositoryId) return;
    const version = requestVersion.current;
    const ensureCurrent = (result: AnalysisResultData) => {
      if (requestVersion.current !== version) throw new ApiError('conflict', 'Repository changed during analysis. Reload to use its current snapshot.');
      return assertAnalysisSnapshot(result, expectedRepository.id, expectedRepository.commit_sha);
    };
    setBusy(true);
    setAnalysis(null);
    setReport('queued');
    setReportError(null);
    try {
      const accepted = await api.startAnalysis(repositoryId);
      if (accepted.commit_sha !== expectedRepository.commit_sha) throw new ApiError('conflict', 'Repository changed during analysis. Reload to use its current snapshot.');
      if (accepted.analysis_id) {
        const result = ensureCurrent(await api.getAnalysis(repositoryId, accepted.analysis_id));
        setAnalysis(result);
        setReport('ready');
      } else if (accepted.job_id) {
        setReport('running');
        let completed: AnalysisResultData | null = null;
        for (let count = 0; count < 90; count += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          const job = await api.getJob(repositoryId, accepted.job_id);
          if (job.commit_sha !== expectedRepository.commit_sha) throw new ApiError('conflict', 'Repository changed during analysis. Reload to use its current snapshot.');
          if (['completed', 'partial', 'failed', 'cancelled'].includes(job.status) && job.analysis_id) {
            completed = ensureCurrent(await api.getAnalysis(repositoryId, job.analysis_id));
            break;
          }
          if (job.status === 'failed' || job.status === 'cancelled') {
            throw new ApiError('failed', job.error_code ?? `Analysis ${job.status}`);
          }
        }
        if (!completed) throw new ApiError('unavailable', 'Analysis is still running. Refresh later to check its result.');
        setAnalysis(completed);
        setReport('ready');
      } else {
        throw new ApiError('failed', 'The API did not return an analysis or job identifier.');
      }
    } catch (error) {
      if (requestVersion.current === version) {
        setAnalysis(null);
        setReportError(error);
        setReport(error instanceof ApiError && error.kind === 'unauthorized' ? 'unauthorized' :
          error instanceof ApiError && error.kind === 'unavailable' ? 'unavailable' : 'error');
      }
    } finally {
      if (requestVersion.current === version) setBusy(false);
    }
  }

  const sourceFiles = tree && inventory === 'ready' ? tree.files.filter((file) => file.included).length : '—';
  const repositoryIsCurrent = repository?.id === repositoryId;
  const visibleAnalysis = repositoryIsCurrent && analysis && analysis.snapshot.repository_id === repository.id && analysis.snapshot.commit_sha === repository.commit_sha ? analysis : null;
  const findingCount = visibleAnalysis ? visibleAnalysis.findings.length : '—';
  const languageCount = tree && inventory === 'ready' ? new Set(tree.files.filter((file) => file.included && file.language).map((file) => file.language)).size : '—';

  if (view === 'loading' || (repository && repository.id !== repositoryId)) return <section className="feature-loading" aria-busy="true" aria-live="polite"><span className="loading-orbit"/>Loading repository overview…</section>;
  if (!repository) return <section className="feature-page"><FeatureNotice title={view === 'unauthorized' ? 'Sign in required' : 'Repository unavailable'}>{view === 'unauthorized' ? <>{messageFor(new ApiError('unauthorized', ''))} <SessionAction/></> : messageFor(new ApiError(view === 'unavailable' ? 'unavailable' : 'failed', ''))}</FeatureNotice><button className="subtle-button" type="button" onClick={() => setAttempt((count) => count + 1)}>Retry</button></section>;

  return <section className="feature-page overview-page">
    {demoMode.verified && <div className="demo-banner" role="note"><strong>LOCAL DEMO FIXTURE</strong><span>Synthetic repository and analysis data. This is not a real repository or live API report.</span></div>}
    <div className="feature-heading"><div><p className="eyebrow">REPOSITORY OVERVIEW</p><h1>{repository.name}</h1><p className="feature-subtitle">{repository.branch} <span aria-hidden="true">·</span> <code>{repository.commit_sha.slice(0, 7)}</code></p></div>
      {!demoMode.verified && <button className="primary-button analysis-action" type="button" onClick={runAnalysis} disabled={busy}>{busy ? <><span className="button-spinner"/> Analyzing</> : 'Run analysis'}</button>}
    </div>

    <div className="overview-metrics" aria-label="Repository metrics">
      <Metric label="Source files" value={sourceFiles} note="Included source files"/>
      <Metric label="Languages" value={languageCount} note="Detected in selected sources"/>
      <Metric label="Findings" value={findingCount} note={visibleAnalysis ? `${statusLabel(visibleAnalysis.status)} report` : 'Run analysis to calculate'}/>
    </div>

    <section className="overview-section technology-section" aria-labelledby="technology-title">
      <div className="section-title-row"><div><span className="section-kicker">CODEBASE PROFILE</span><h2 id="technology-title">Languages and frameworks</h2></div><span className="source-chip">Current snapshot</span></div>
      <div className="technology-columns"><div><h3>Languages</h3>{inventory === 'loading' ? <p className="muted-copy">Loading file inventory…</p> : inventory === 'unauthorized' ? <p className="muted-copy">Session access is required to read the file inventory. <SessionAction/></p> : inventory === 'unavailable' || inventory === 'error' ? <><p className="muted-copy">{inventory === 'unavailable' ? 'File inventory is currently unavailable.' : 'File inventory could not be verified for this snapshot.'}</p><button className="subtle-button" type="button" onClick={() => setAttempt((count) => count + 1)}>Retry inventory</button></> : tree && tree.files.some((file) => file.included && file.language) ? <ul className="technology-list">{Object.entries(tree.files.filter((file) => file.included && file.language).reduce<Record<string, number>>((counts, file) => { counts[file.language!] = (counts[file.language!] ?? 0) + 1; return counts; }, {})).map(([language, count]) => <li key={language}><span>{language}</span><strong>{count}</strong></li>)}</ul> : <p className="muted-copy">No included language data is available.</p>}</div>
        <div><h3>Frameworks</h3>{repository.frameworks.length ? <div className="framework-chips">{repository.frameworks.map((framework) => <span key={framework}>{framework}</span>)}</div> : <p className="muted-copy">No framework markers detected.</p>}</div></div>
    </section>

    <section className="overview-section analysis-section" aria-labelledby="analysis-title">
      <div className="section-title-row"><div><span className="section-kicker">ANALYSIS</span><h2 id="analysis-title">Current report</h2></div>{visibleAnalysis && <span className={`analysis-badge status-${visibleAnalysis.status}`}><i aria-hidden="true"/>{statusLabel(visibleAnalysis.status)}</span>}</div>
      {report === 'loading' && <div className="inline-loading" aria-busy="true"><span className="loading-orbit"/>Checking for a report…</div>}
      {(report === 'queued' || report === 'running') && <div className="progress-panel" role="status"><span className="loading-orbit"/><div><strong>{report === 'queued' ? 'Analysis queued' : 'Analysis in progress'}</strong><p>The worker is checking the current repository snapshot.</p></div></div>}
      {report === 'empty' && <FeatureNotice title="No analysis for this snapshot yet">Start an analysis to see verified findings and role status.</FeatureNotice>}
      {(report === 'unauthorized' || report === 'unavailable' || report === 'error') && <FeatureNotice title={report === 'unauthorized' ? 'Session required' : report === 'unavailable' ? 'Report unavailable' : 'Could not load report'} onRetry={report === 'unauthorized' ? undefined : () => setAttempt((count) => count + 1)}>{messageFor(reportError)}{report === 'unauthorized' && <> <SessionAction/></>}</FeatureNotice>}
      {visibleAnalysis && report === 'ready' && <div className={`report-summary ${visibleAnalysis.status === 'partial' || visibleAnalysis.status === 'failed' ? 'has-warning' : ''}`}>
        <p>{visibleAnalysis.status === 'succeeded' ? 'The current snapshot has a complete analysis report.' : visibleAnalysis.status === 'partial' ? 'Some analysis roles completed; the report includes the errors and results that were available.' : visibleAnalysis.status === 'failed' ? 'The analysis did not complete. Its errors are shown below.' : `The report status is ${visibleAnalysis.status}.`}</p>
        {visibleAnalysis.schema_version === 2 && <div className="role-list" aria-label="Analysis role results">{visibleAnalysis.roles.map((role) => <div className="role-row" key={role.role}><span>{role.role}</span><span className={`role-state role-${role.status}`}>{role.status.replace('_', ' ')}</span></div>)}</div>}
        {visibleAnalysis.errors.length > 0 && <ul className="report-errors">{visibleAnalysis.errors.map((error, index) => <li key={`${error.code}-${index}`}><strong>{error.code}</strong> {error.message}</li>)}</ul>}
        {visibleAnalysis.findings.length > 0 && <div className="finding-preview"><span className="section-kicker">LATEST FINDING</span><p>{visibleAnalysis.findings[0].description}</p><small>{visibleAnalysis.findings[0].location.path}:{visibleAnalysis.findings[0].location.start_line} · {visibleAnalysis.findings[0].severity}</small></div>}
      </div>}
      {!demoMode.verified && report === 'empty' && <button className="primary-button analysis-action" type="button" onClick={runAnalysis} disabled={busy}>{busy ? 'Starting analysis…' : 'Start analysis'}</button>}
    </section>
  </section>;
}
