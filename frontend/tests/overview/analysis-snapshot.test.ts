import { describe, expect, it } from 'vitest';
import { assertAnalysisSnapshot } from '../../src/features/overview/OverviewPage';
import { ApiError, type AnalysisResultData } from '../../src/features/overview/api';

const analysis = (repositoryId: string, commitSha: string) => ({
  snapshot: { repository_id: repositoryId, commit_sha: commitSha },
} as AnalysisResultData);

describe('overview analysis snapshot boundary', () => {
  it('accepts only the analysis for the displayed repository and commit', () => {
    const current = analysis('repo-1', 'a'.repeat(40));
    expect(assertAnalysisSnapshot(current, 'repo-1', 'a'.repeat(40))).toBe(current);
    expect(assertAnalysisSnapshot(null, 'repo-1', 'a'.repeat(40))).toBeNull();
  });

  it.each([
    ['a different repository', analysis('repo-2', 'a'.repeat(40)), 'repo-1', 'a'.repeat(40)],
    ['a stale commit from a request race', analysis('repo-1', 'b'.repeat(40)), 'repo-1', 'a'.repeat(40)],
  ])('rejects an analysis for %s', (_case, result, repositoryId, commitSha) => {
    expect(() => assertAnalysisSnapshot(result as AnalysisResultData, repositoryId as string, commitSha as string))
      .toThrowError(expect.objectContaining({ kind: 'conflict' }) as ApiError);
  });
});
