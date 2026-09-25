import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { App, resolveRoute } from '../../src/app/App';

describe('repository overview and file routes', () => {
  it('routes the repository file page separately from the overview', () => {
    expect(resolveRoute('/repository/repo-42')).toMatchObject({ page: 'repository', repositoryId: 'repo-42', repositoryView: 'overview' });
    expect(resolveRoute('/repository/repo-42/files')).toMatchObject({ page: 'repository', repositoryId: 'repo-42', repositoryView: 'files' });
    expect(resolveRoute('/repository/repo-42/files/deeper')).toMatchObject({ page: 'not-found' });
  });

  it('protects the file page until server-session verification completes', () => {
    const html = renderToStaticMarkup(App({ pathname: '/repository/repo-42/files' }));
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('Loading repository file tree');
  });

  it('protects the API-backed overview until server-session verification completes', () => {
    const html = renderToStaticMarkup(App({ pathname: '/repository/repo-42' }));
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('Repository details are not connected yet');
  });
});
