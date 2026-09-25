import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { App, resolveRoute } from '../../src/app/App';

describe('repository architecture routes', () => {
  it('routes architecture and dependencies as separate repository views', () => {
    expect(resolveRoute('/repository/repo-42/architecture')).toMatchObject({
      page: 'repository', repositoryId: 'repo-42', repositoryView: 'architecture',
    });
    expect(resolveRoute('/repository/repo-42/dependencies')).toMatchObject({
      page: 'repository', repositoryId: 'repo-42', repositoryView: 'dependencies',
    });
  });

  it('protects the architecture screen until server-session verification completes', () => {
    const html = renderToStaticMarkup(App({ pathname: '/repository/repo-42/architecture' }));
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('Loading architecture report');
  });

  it('protects the dependency screen until server-session verification completes', () => {
    const html = renderToStaticMarkup(App({ pathname: '/repository/repo-42/dependencies' }));
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('Loading dependency report');
  });
});
