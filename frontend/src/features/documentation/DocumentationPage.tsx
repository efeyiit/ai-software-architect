import type { AnalysisResultData, RepositoryInfo } from '../overview/api';
import { CopyDownload, ReportPage } from '../findings/use-analysis-report';
import { sourceHref } from '../architecture/source-links';

function DocumentationResults({ repository, analysis }: { repository: RepositoryInfo; analysis: AnalysisResultData }) {
  const data = analysis.schema_version === 2 ? analysis.documentation : null;
  if (!data) return <section className="report-section"><h2>Documentation draft unavailable</h2><p className="report-muted">This report version does not include documentation fields.</p></section>;
  const readme = data.readme; const api = data.api_markdown;
  return <><div className="report-warning" role="note"><strong>Draft output.</strong> Review every generated statement before using it as project documentation. Rendering is plain text; repository markdown and HTML are inert.</div>
    <section className="report-section"><div className="report-section-heading"><div><span className="draft-label">README · draft</span><h2>README draft</h2></div><CopyDownload value={readme} filename="README-draft.md"/></div><pre className="report-code report-markdown">{readme || 'No README draft returned.'}</pre></section>
    <section className="report-section"><div className="report-section-heading"><div><span className="draft-label">API documentation · draft</span><h2>API reference draft</h2></div><CopyDownload value={api} filename="api-documentation-draft.md"/></div><pre className="report-code report-markdown">{api || 'No API draft returned.'}</pre>{data.routes.length > 0 && <ul className="report-rows">{data.routes.map((route, index) => <li key={`${route.method}:${route.path}:${index}`}><div><strong>{route.method} {route.path}</strong><span>Draft route · {route.evidence.path}:{route.evidence.line}</span></div><a href={sourceHref(repository, route.evidence.path, route.evidence.line) ?? undefined}>View source</a></li>)}</ul>}</section>
    <section className="report-section"><h2>Source-backed facts</h2>{data.facts.length ? <ul className="report-rows">{data.facts.map((fact, index) => <li key={`${fact.evidence.path}:${fact.evidence.line}:${index}`}><span>{fact.text}</span><a href={sourceHref(repository, fact.evidence.path, fact.evidence.line) ?? undefined}>{fact.evidence.path}:{fact.evidence.line}</a></li>)}</ul> : <p className="report-muted">No source-backed facts returned.</p>}</section>
    {data.uncertainties.length > 0 && <section className="report-section"><h2>Uncertainties</h2><ul>{data.uncertainties.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}</>;
}
export function DocumentationPage({ repositoryId }: { repositoryId: string }) { return <ReportPage repositoryId={repositoryId} eyebrow="DOCUMENTATION OUTPUT" title="Documentation">{(repository, analysis) => <DocumentationResults repository={repository} analysis={analysis}/>}</ReportPage>; }
