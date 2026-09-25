import { useState } from 'react';
import type { AnalysisResultData, RepositoryInfo } from '../overview/api';
import { sourceHref } from '../architecture/source-links';
import { CopyDownload, ReportPage } from './use-analysis-report';

type Finding = AnalysisResultData['findings'][number];
export function filterFindings(findings: Finding[], severity: string, source: string) {
  return findings.filter((finding) => (severity === 'all' || finding.severity === severity) && (source === 'all' || finding.source === source));
}
export function securityFindingIds(analysis: AnalysisResultData) {
  return analysis.schema_version === 2 ? new Set(analysis.items.filter((item) => item.roles.includes('security') && item.finding).map((item) => item.finding!.id)) : new Set<string>();
}
export function exportFindings(findings: Finding[], securityIds: Set<string>) {
  return findings.map((item) => securityIds.has(item.id) ? `${item.severity.toUpperCase()} · ${item.source}\nPotential security signal: sensitive text withheld\n${item.location.path}:${item.location.start_line}` : `${item.severity.toUpperCase()} · ${item.source}\n${item.issue_type}: ${item.description}\n${item.location.path}:${item.location.start_line}`).join('\n\n');
}
function FindingList({ repository, findings, securityIds = new Set<string>() }: { repository: RepositoryInfo; findings: Finding[]; securityIds?: Set<string> }) {
  if (!findings.length) return <div className="report-empty"><strong>No matching findings</strong><p>The current analysis returned no results for this selection.</p></div>;
  return <ul className="finding-list">{findings.map((finding) => { const href = sourceHref(repository, finding.location.path, finding.location.start_line); return <li className="finding-card" key={finding.id}>
    <div className="finding-card-heading"><span className={`severity severity-${finding.severity}`}>{finding.severity}</span>{securityIds.has(finding.id) && <span className="possible-risk">Possible security risk</span>}<span className={`finding-origin origin-${finding.source}`}>{finding.source === 'static' ? 'Static evidence' : 'AI interpretation'}</span></div>
    <h3>{securityIds.has(finding.id) ? 'Potential security signal' : finding.issue_type.replaceAll('_', ' ')}</h3>{securityIds.has(finding.id) ? <p>Potential signal only. Sensitive source text is intentionally withheld.</p> : <p>{finding.description}</p>}
    {!securityIds.has(finding.id) && finding.suggestion && <details><summary>Suggested follow-up</summary><p>{finding.suggestion}</p></details>}
    <a className="report-source-link" href={href ?? undefined} target={href ? '_blank' : undefined} rel={href ? 'noopener noreferrer' : undefined}>{finding.location.path}:{finding.location.start_line}{finding.location.end_line !== finding.location.start_line ? `–${finding.location.end_line}` : ''}</a>
  </li>; })}</ul>;
}

export function FindingsPage({ repositoryId }: { repositoryId: string }) {
  const [severity, setSeverity] = useState('all'); const [source, setSource] = useState('all');
  return <ReportPage repositoryId={repositoryId} eyebrow="ANALYSIS FINDINGS" title="Findings">{(repository, analysis) => {
    const filtered = filterFindings(analysis.findings, severity, source);
    const hiddenValues = securityFindingIds(analysis);
    const exportText = exportFindings(analysis.findings, hiddenValues);
    return <><div className="report-toolbar"><label>Severity <select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">All severities</option>{['critical','high','medium','low','info'].map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label>Source type <select value={source} onChange={(event) => setSource(event.target.value)}><option value="all">All sources</option><option value="static">Static evidence</option><option value="ai">AI interpretation</option></select></label><span>{filtered.length} of {analysis.findings.length} findings</span></div><section className="report-section"><h2>Repository findings</h2><p className="report-muted">Static evidence and AI interpretation are labeled separately. Links are pinned to commit <code>{analysis.snapshot.commit_sha}</code>.</p><FindingList repository={repository} findings={filtered} securityIds={hiddenValues}/></section><section className="report-section"><h2>Refactoring recommendations</h2>{analysis.schema_version === 2 && analysis.refactoring ? analysis.refactoring.recommendations.length ? <ul className="finding-list">{analysis.refactoring.recommendations.map((item, index) => <li className="finding-card" key={`${item.subject}:${index}`}><span className="draft-label">Candidate · deterministic</span><h3>{item.subject}</h3><p>{item.rationale}</p><a className="report-source-link" href={sourceHref(repository, item.location.path, item.location.start_line) ?? undefined}>{item.location.path}:{item.location.start_line}</a></li>)}</ul> : <p className="report-muted">No refactoring candidates were returned.</p> : <p className="report-muted">Refactoring data is unavailable in this report version.</p>}</section><section className="report-section"><h2>Report export</h2><pre className="report-code">{exportText || 'No findings returned.'}</pre><CopyDownload value={exportText} filename="ariadne-findings.txt"/></section></>;
  }}</ReportPage>;
}
