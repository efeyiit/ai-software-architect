import { describe, expect, it } from 'vitest';
import { exportFindings, filterFindings } from '../../src/features/findings/FindingsPage';
import { sourceHref } from '../../src/features/architecture/source-links';
import { parseAnalysisResult } from '../../src/contracts/analysis';

const finding = (id: string, severity: 'high' | 'low', source: 'static' | 'ai') => ({ id, severity, source, issue_type: 'test', location: { path: 'src/app.ts', start_line: 4, end_line: 4 }, description: 'example', suggestion: null });
const findings = [finding('a', 'high', 'static'), finding('b', 'low', 'ai')];

describe('findings view boundaries', () => {
  it('filters severity and evidence source independently', () => {
    expect(filterFindings(findings, 'high', 'all').map((item) => item.id)).toEqual(['a']);
    expect(filterFindings(findings, 'all', 'ai').map((item) => item.id)).toEqual(['b']);
    expect(filterFindings(findings, 'critical', 'all')).toEqual([]);
  });
  it('withholds security-associated source text from finding exports', () => {
    const output = exportFindings([finding('secret', 'high', 'static')], new Set(['secret']));
    expect(output).toContain('sensitive text withheld');
    expect(output).not.toContain('example');
  });
  it('pins source links to the repository commit and rejects unsafe inputs', () => {
    const repository = { github_url: 'https://github.com/acme/project', commit_sha: 'a'.repeat(40) } as never;
    expect(sourceHref(repository, 'src/app.ts', 4)).toBe(`https://github.com/acme/project/blob/${'a'.repeat(40)}/src/app.ts#L4`);
    expect(sourceHref(repository, '../secret', 1)).toBeNull();
  });
  it('accepts v2 coverage/test/doc contracts without inventing absent data', () => {
    const parsed = parseAnalysisResult({ schema_version: 2, analysis_id: 'a1', snapshot: { repository_id: 'r1', commit_sha: 'a'.repeat(40) }, status: 'partial', findings: [], errors: [{ code: 'ROLE_FAILED', message: 'failed', retryable: true, location: null }], partial: true, ai_status: 'unavailable', roles: ['architect','security','testing','refactoring','documentation'].map((role) => ({ role, status: role === 'testing' ? 'failed' : 'succeeded', error_code: null })), items: [], conflicts: [], architecture: null, testing: { test_files: [], services: [], coverage: null, coverage_status: 'missing', coverage_errors: [] }, refactoring: null, documentation: { snapshot: { repository_id: 'r1', commit_sha: 'a'.repeat(40) }, ai_status: 'unavailable', readme: '<img src=x onerror=alert(1)>', api_markdown: '', facts: [], routes: [], uncertainties: [] }, dependencies: null });
    expect(parsed.schema_version).toBe(2);
    if (parsed.schema_version === 2) {
      expect(parsed.testing?.coverage).toBeNull();
      expect(parsed.documentation?.readme).toContain('<img');
    }
  });
});
