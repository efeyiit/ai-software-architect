import { afterEach, describe, expect, it, vi } from 'vitest';
import { AriadneApi, ApiError } from '../../src/features/overview/api';

afterEach(() => vi.unstubAllGlobals());

describe('AriadneApi browser security boundary', () => {
  it('uses the session cookie and fetched CSRF token without a client identity header', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ user_id: 'owner', csrf_token: 'csrf-from-session' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'queued', job_id: 'job-1', commit_sha: 'a'.repeat(40) })));
    vi.stubGlobal('fetch', fetchMock);
    const api = new AriadneApi();

    await api.startAnalysis('repo-1');

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/auth/me', '/api/repositories/repo-1/analyze',
    ]);
    const [url, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/repositories/repo-1/analyze');
    expect(options.credentials).toBe('include');
    expect(new Headers(options.headers).get('X-Ariadne-CSRF')).toBe('csrf-from-session');
    expect(new Headers(options.headers).has('X-User-Id')).toBe(false);
  });

  it('keeps unauthorized responses distinct from unavailable services', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'session_required' }), { status: 401 },
    )));
    const api = new AriadneApi();

    await expect(api.getRepository('repo-1')).rejects.toMatchObject({ kind: 'unauthorized' });
  });

  it('maps a missing files capability to an explicit unavailable state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'not_found' }), { status: 404 },
    )));
    const api = new AriadneApi();

    await expect(api.getFiles('repo-1')).rejects.toMatchObject({ kind: 'unavailable' });
  });

  it('requests a file summary by encoded relative path without sending source contents', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      snapshot: { repository_id: 'repo-1', commit_sha: 'a'.repeat(40) }, ai_status: 'unavailable', path: 'src/a.ts',
      responsibility: 'Unknown from parsed structure alone.', responsibility_citations: [], structural_facts: [],
      ai_claims: [], uncertainties: ['Business responsibility is unknown.'],
    })));
    vi.stubGlobal('fetch', fetchMock);
    const api = new AriadneApi();

    await api.getFileSummary('repo-1', 'src/a.ts');

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/repositories/repo-1/files/summary?path=src%2Fa.ts');
    expect(options.method).toBeUndefined();
    expect(options.body).toBeUndefined();
    expect(options.credentials).toBe('include');
  });

  it('keeps missing summaries distinct from a missing summary capability', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'file_unavailable' }), { status: 404 },
    )));
    const api = new AriadneApi();

    await expect(api.getFileSummary('repo-1', 'src/a.ts')).rejects.toMatchObject({ kind: 'not_found', code: 'file_unavailable' });
  });

  it('treats an absent current analysis as an empty state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'analysis_unavailable' }), { status: 404 },
    )));
    const api = new AriadneApi();

    await expect(api.getLatestAnalysis('repo-1')).resolves.toBeNull();
  });
});
