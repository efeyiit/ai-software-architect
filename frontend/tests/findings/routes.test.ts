import { describe, expect, it } from 'vitest';
import { resolveRoute } from '../../src/app/App';

describe('T29 routes', () => {
  it.each(['findings', 'security', 'testing', 'documentation'] as const)('resolves %s repository screen', (view) => {
    expect(resolveRoute(`/repository/repo-1/${view}`)).toEqual({ page: 'repository', repositoryId: 'repo-1', repositoryView: view });
  });
  it('keeps malformed encoded repository ids on not-found', () => {
    expect(resolveRoute('/repository/%E0%A4%A/security')).toEqual({ page: 'not-found' });
  });
});
