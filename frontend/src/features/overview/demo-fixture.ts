import type { AnalysisResultData, FileSummary, RepositoryFile, RepositoryInfo } from './api';

const sha = '0123456789abcdef0123456789abcdef01234567';
export const demoSnapshot = { repository_id: 'demo-commerce-api', commit_sha: sha };
export const demoRepository: RepositoryInfo = {
  id: demoSnapshot.repository_id, github_url: 'https://github.com/ariadne-demo/commerce-api',
  name: 'commerce-api', branch: 'main', commit_sha: sha,
  languages: { TypeScript: 42, JSON: 8 }, frameworks: ['Node.js', 'Express'],
};
export const demoFiles: RepositoryFile[] = [
  { path: 'src/api/orders.ts', language: 'TypeScript', included: true, size: 1840, exclusion_reason: null },
  { path: 'src/api/users.ts', language: 'TypeScript', included: true, size: 920, exclusion_reason: null },
  { path: 'package.json', language: 'JSON', included: false, size: 412, exclusion_reason: 'unsupported_parser' },
];
export const demoSummary: FileSummary = {
  snapshot: demoSnapshot, ai_status: 'unavailable', path: 'src/api/orders.ts',
  responsibility: 'Unknown from parsed structure alone.', responsibility_citations: [],
  structural_facts: [{ text: 'Defines function createOrder.', origin: 'static', citations: [{
    location: { path: 'src/api/orders.ts', start_line: 18, end_line: 18 }, quote: null,
  }] }], ai_claims: [], uncertainties: ['Business responsibility cannot be established from syntax alone.'],
};
export const demoAnalysis: AnalysisResultData = {
  schema_version: 2, analysis_id: 'demo-analysis-01', snapshot: demoSnapshot,
  status: 'partial', findings: [{ id: 'demo-finding-01', source: 'static', issue_type: 'long_function', severity: 'medium',
    location: { path: 'src/api/orders.ts', start_line: 18, end_line: 51 },
    description: 'The order creation function has several responsibilities.', suggestion: null }],
  errors: [{ code: 'ROLE_TIMEOUT', message: 'Documentation analysis timed out in this demo fixture.', retryable: true, location: null }],
  partial: true, ai_status: 'unavailable',
  roles: [
    { role: 'architect', status: 'succeeded', error_code: null }, { role: 'security', status: 'succeeded', error_code: null },
    { role: 'testing', status: 'succeeded', error_code: null }, { role: 'refactoring', status: 'succeeded', error_code: null },
    { role: 'documentation', status: 'timed_out', error_code: 'ROLE_TIMEOUT' },
  ],
  items: [{ id: 'demo-item-01', kind: 'static_finding', roles: ['refactoring'], origin: 'static',
    location: { path: 'src/api/orders.ts', start_line: 18, end_line: 51 },
    text: 'The order creation function has several responsibilities.',
    finding: { id: 'demo-finding-01', source: 'static', issue_type: 'long_function', severity: 'medium',
      location: { path: 'src/api/orders.ts', start_line: 18, end_line: 51 },
      description: 'The order creation function has several responsibilities.', suggestion: null } }],
  conflicts: [], architecture: null, testing: null, refactoring: null, documentation: null, dependencies: null,
};
