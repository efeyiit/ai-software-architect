import { z } from 'zod';

const repositorySchema = z.strictObject({ id: z.string().min(1), github_url: z.string().url(), name: z.string().min(1), commit_sha: z.string().regex(/^[0-9a-f]{40}$/) });
const listSchema = z.array(repositorySchema);
export type RepositoryEntry = z.infer<typeof repositorySchema>;

export class RepositoryApiError extends Error {
  constructor(readonly code: string, readonly status?: number) { super(code); this.name = 'RepositoryApiError'; }
}

async function parseResponse(response: Response) {
  let body: unknown;
  try { body = await response.json(); } catch { body = undefined; }
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body ? (body as { detail: unknown }).detail : '';
    const code = typeof detail === 'string' ? detail : typeof detail === 'object' && detail !== null && 'code' in detail && typeof detail.code === 'string' ? detail.code : `http_${response.status}`;
    throw new RepositoryApiError(code, response.status);
  }
  return body;
}

export const repositoryApi = {
  async list(): Promise<RepositoryEntry[]> {
    let response: Response;
    try { response = await fetch('/api/repositories', { credentials: 'include', headers: { Accept: 'application/json' } }); }
    catch { throw new RepositoryApiError('service_unavailable'); }
    const body = await parseResponse(response);
    const parsed = listSchema.safeParse(body);
    if (!parsed.success) throw new RepositoryApiError('invalid_repository_list', response.status);
    return parsed.data;
  },
  async create(githubUrl: string, csrfToken: string): Promise<RepositoryEntry> {
    let response: Response;
    try { response = await fetch('/api/repositories', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Ariadne-CSRF': csrfToken }, body: JSON.stringify({ github_url: githubUrl }) }); }
    catch { throw new RepositoryApiError('service_unavailable'); }
    const body = await parseResponse(response);
    const parsed = repositorySchema.safeParse(body);
    if (!parsed.success) throw new RepositoryApiError('invalid_repository_response', response.status);
    return parsed.data;
  },
};
