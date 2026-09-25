import { afterEach, describe, expect, it, vi } from 'vitest';
import { repositoryApi } from '../../src/features/repositories/api';

afterEach(() => vi.unstubAllGlobals());

const repository = { id: 'repo-1', github_url: 'https://github.com/acme/service', name: 'service', commit_sha: 'a'.repeat(40) };

describe('owner-scoped repository API', () => {
  it('loads the signed-in user repository list with the session cookie', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([repository])));
    vi.stubGlobal('fetch', fetchMock);

    await expect(repositoryApi.list()).resolves.toEqual([repository]);
    expect(fetchMock).toHaveBeenCalledWith('/api/repositories', { credentials: 'include', headers: { Accept: 'application/json' } });
  });

  it('posts the repository URL with the current session CSRF token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(repository), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(repositoryApi.create(repository.github_url, 'csrf-session')).resolves.toEqual(repository);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/repositories');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('include');
    expect(JSON.parse(String(options.body))).toEqual({ github_url: repository.github_url });
    expect(new Headers(options.headers).get('X-Ariadne-CSRF')).toBe('csrf-session');
  });

  it('preserves authorization and validation errors without claiming a connection', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'login_required' } }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'invalid_github_url' } }), { status: 422 })));

    await expect(repositoryApi.create(repository.github_url, 'csrf')).rejects.toMatchObject({ code: 'login_required', status: 401 });
    await expect(repositoryApi.create(repository.github_url, 'csrf')).rejects.toMatchObject({ code: 'invalid_github_url', status: 422 });
  });

  it('rejects a repository-list payload that does not match the API contract', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ repositories: [repository] }))));

    await expect(repositoryApi.list()).rejects.toMatchObject({ code: 'invalid_repository_list' });
  });
});
