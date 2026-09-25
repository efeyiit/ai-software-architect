import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { App, resolveRoute } from '../../src/app/App';

describe('application shell', () => {
  it('resolves login, dashboard, repository, and unknown paths while hiding the retired demo route', () => {
    expect(resolveRoute('/login').page).toBe('login');
    expect(resolveRoute('/dashboard').page).toBe('dashboard');
    expect(resolveRoute('/repository/acme-api').page).toBe('repository');
    expect(resolveRoute('/not-a-page').page).toBe('not-found');
    expect(resolveRoute('/demo').page).toBe('not-found');
  });

  it('keeps workspace pages behind the initial server-session check', () => {
    const html = renderToStaticMarkup(App({ pathname: '/dashboard' }));
    expect(html).toContain('Checking your session');
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain('No repositories connected');
    expect(html).not.toContain('Yerel demo');
  });

  it('keeps the login route in an explicit loading state until /auth/me resolves', () => {
    const html = renderToStaticMarkup(App({ pathname: '/login' }));
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('Continue with GitHub');
  });

  it('does not expose a protected repository before the server-session check', () => {
    const html = renderToStaticMarkup(App({ pathname: '/repository/example' }));
    expect(html).toContain('Checking your session');
    expect(html).not.toContain('0 files');
  });
});
