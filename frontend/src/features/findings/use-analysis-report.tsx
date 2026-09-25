import { useEffect, useState, type ReactNode } from 'react';
import { AriadneApi, ApiError, type AnalysisResultData, type RepositoryInfo } from '../overview/api';
import { FeatureNotice, SessionAction } from '../overview/SessionAction';
import { useDemoMode } from '../demo/DemoMode';
import '../overview/overview.css';
import './findings.css';

const api = new AriadneApi();
export type ReportState = { status: 'loading' } | { status: 'error'; error: unknown } |
  { status: 'ready'; repository: RepositoryInfo; analysis: AnalysisResultData | null };

export function useAnalysisReport(repositoryId: string) {
  const demoMode = useDemoMode();
  const [state, setState] = useState<ReportState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState({ status: 'loading' });
    if (demoMode.loading) return () => { active = false; };
    if (demoMode.verified) {
      import('../overview/demo-fixture').then(({ demoAnalysis, demoRepository }) => {
        if (!active) return;
        if (demoRepository.id !== repositoryId) { setState({ status: 'error', error: new ApiError('conflict', 'Fixture and route refer to different repositories.') }); return; }
        setState({ status: 'ready', repository: demoRepository, analysis: demoAnalysis });
      });
      return () => { active = false; };
    }
    Promise.all([api.getRepository(repositoryId), api.getLatestAnalysis(repositoryId)]).then(([repository, analysis]) => {
      if (!active) return;
      if (analysis && (analysis.snapshot.repository_id !== repositoryId || analysis.snapshot.commit_sha !== repository.commit_sha))
        throw new ApiError('conflict', 'Analysis belongs to a different repository snapshot.');
      setState({ status: 'ready', repository, analysis });
    }).catch((error: unknown) => { if (active) setState({ status: 'error', error }); });
    return () => { active = false; };
  }, [repositoryId, attempt, demoMode.loading, demoMode.verified]);
  return { state, retry: () => setAttempt((value) => value + 1) };
}

export function ControlledFixtureBanner() {
  const demoMode = useDemoMode();
  return demoMode.verified
    ? <div className="demo-banner" role="note"><strong>LOCAL DEMO FIXTURE</strong><span>Bundled synthetic repository report. This is not live repository or authentication evidence.</span></div>
    : null;
}

export function ReportPage({ repositoryId, eyebrow, title, children }: { repositoryId: string; eyebrow: string; title: string; children: (repository: RepositoryInfo, analysis: AnalysisResultData) => ReactNode }) {
  const { state, retry } = useAnalysisReport(repositoryId);
  if (state.status === 'loading') return <section className="feature-loading" aria-busy="true" aria-live="polite"><span className="loading-orbit"/>Loading {title.toLowerCase()}…</section>;
  if (state.status === 'error') {
    const unauthorized = state.error instanceof ApiError && state.error.kind === 'unauthorized';
    const unavailable = state.error instanceof ApiError && state.error.kind === 'unavailable';
    return <section className="feature-page report-page"><ControlledFixtureBanner/><FeatureNotice title={unauthorized ? 'Sign in required' : unavailable ? 'Ariadne API unavailable' : 'Could not load report'} onRetry={unauthorized ? undefined : retry}>{unauthorized ? <>Your session is missing or expired. <SessionAction/></> : unavailable ? 'The API is unavailable. No sample report is shown in live mode.' : 'The report could not be validated or does not match the current repository snapshot.'}</FeatureNotice></section>;
  }
  return <section className="feature-page report-page"><ControlledFixtureBanner/><header className="feature-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="feature-subtitle">{state.repository.name} · <code>{state.repository.commit_sha.slice(0, 7)}</code></p></div>{state.analysis && <span className={`analysis-badge status-${state.analysis.status}`}><i aria-hidden="true"/>{state.analysis.status === 'partial' ? 'Partial results' : state.analysis.status}</span>}</header>
    {!state.analysis ? <FeatureNotice title="No analysis for this snapshot">Run an analysis from the repository overview to see current report data.</FeatureNotice> : <>{state.analysis.status === 'partial' && <div className="report-warning" role="status"><strong>Partial report.</strong> Some analysis roles failed or timed out; review errors before relying on this view.</div>}{state.analysis.errors.length > 0 && <details className="report-errors-panel"><summary>Report errors ({state.analysis.errors.length})</summary><ul>{state.analysis.errors.map((error, index) => <li key={`${error.code}:${index}`}><strong>{error.code}</strong> {error.message}</li>)}</ul></details>}{children(state.repository, state.analysis)}</>}
  </section>;
}

export function CopyDownload({ value, filename }: { value: string; filename: string }) {
  const [feedback, setFeedback] = useState('');
  async function copy() {
    try { await navigator.clipboard.writeText(value); setFeedback('Copied to clipboard.'); }
    catch { setFeedback('Clipboard access was denied. Select the text and copy it manually.'); }
  }
  function download() {
    try { const url = URL.createObjectURL(new Blob([value], { type: 'text/markdown;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); setFeedback(`Downloaded ${filename}.`); }
    catch { setFeedback('Download could not be started.'); }
  }
  return <div className="report-actions"><button type="button" className="subtle-button" onClick={() => void copy()}>Copy</button><button type="button" className="subtle-button" onClick={download}>Download</button><span aria-live="polite" role="status">{feedback}</span></div>;
}
