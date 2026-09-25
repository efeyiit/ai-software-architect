import type { AnalysisResultData, RepositoryInfo } from '../overview/api';
import { ReportPage } from '../findings/use-analysis-report';
import { sourceHref } from '../architecture/source-links';

function SecurityResults({ repository, analysis }: { repository: RepositoryInfo; analysis: AnalysisResultData }) {
  if (analysis.schema_version !== 2) return <section className="report-section"><h2>Security report unavailable</h2><p className="report-muted">This report version does not identify security-role findings. The screen will not infer them from unrelated findings.</p></section>;
  const securityIds = new Set(analysis.items.filter((item) => item.roles.includes('security') && item.finding).map((item) => item.finding!.id));
  const findings = analysis.findings.filter((item) => securityIds.has(item.id));
  return <section className="report-section"><h2>Potential security risks</h2><p className="report-muted">Signals are possible risks, not confirmed vulnerabilities. Secret values and source excerpts are never shown here.</p>{findings.length ? <ul className="finding-list">{findings.map((item) => { const href = sourceHref(repository, item.location.path, item.location.start_line); return <li className="finding-card" key={item.id}><div className="finding-card-heading"><span className="possible-risk">Possible security risk</span><span className={`severity severity-${item.severity}`}>{item.severity}</span></div><h3>{item.issue_type.replaceAll('_', ' ')}</h3><p>Potential signal only. Sensitive source text is intentionally withheld.</p><a className="report-source-link" href={href ?? undefined} target={href ? '_blank' : undefined} rel={href ? 'noopener noreferrer' : undefined}>{item.location.path}:{item.location.start_line}</a></li>; })}</ul> : <div className="report-empty"><strong>No security findings returned</strong><p>This means the current analyzer reported no matching signals; it does not prove the repository is secure.</p></div>}</section>;
}

export function SecurityPage({ repositoryId }: { repositoryId: string }) {
  return <ReportPage repositoryId={repositoryId} eyebrow="SECURITY REVIEW" title="Security">{(repository, analysis) => <SecurityResults repository={repository} analysis={analysis}/>}</ReportPage>;
}
