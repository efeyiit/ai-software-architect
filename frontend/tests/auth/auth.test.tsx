import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthApiError, authApi } from '../../src/features/auth/api';
import { LoginPage } from '../../src/features/auth/LoginPage';

afterEach(() => vi.unstubAllGlobals());

describe('server-backed sign-in', () => {
  it('uses the same-origin session cookie and treats 401 as signed out', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'login_required' } }), { status: 401 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(authApi.session()).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledWith('/auth/me', {
      credentials: 'include', headers: { Accept: 'application/json' },
    });
  });

  it('returns the server session and its CSRF token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ user_id: 'owner-1', csrf_token: 'session-csrf' })));
    vi.stubGlobal('fetch', fetchMock);

    await expect(authApi.session()).resolves.toEqual({ user_id: 'owner-1', csrf_token: 'session-csrf' });
  });

  it('distinguishes missing OAuth configuration from an unavailable auth service', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'configuration_unavailable' } }), { status: 503 }))
      .mockResolvedValueOnce(new Response('offline', { status: 502 })));

    await expect(authApi.session()).rejects.toMatchObject({ kind: 'configuration' });
    await expect(authApi.session()).rejects.toMatchObject({ kind: 'unavailable' });
  });

  it('shows OAuth only after a confirmed signed-out response', () => {
    const html = renderToStaticMarkup(<LoginPage state={{ status: 'signed-out' }} retry={() => undefined}/>);
    expect(html).toContain('href="/auth/github/login"');
    expect(html).toContain('Continue with GitHub');
  });

  it('does not show OAuth when server configuration is missing', () => {
    const html = renderToStaticMarkup(<LoginPage state={{ status: 'error', error: new AuthApiError('configuration', 'configuration_unavailable', 503) }} retry={() => undefined}/>);
    expect(html).toContain('GitHub sign-in is not configured');
    expect(html).toContain('Configuration required');
    expect(html).not.toContain('/auth/github/login');
  });

  it('renders a retryable unavailable state without assuming sign-in status', () => {
    const html = renderToStaticMarkup(<LoginPage state={{ status: 'error', error: new AuthApiError('unavailable', 'unavailable', 502) }} retry={() => undefined}/>);
    expect(html).toContain('Sign-in status could not be checked');
    expect(html).toContain('Retry session check');
    expect(html).not.toContain('/auth/github/login');
  });
});
