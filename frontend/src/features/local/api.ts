import { z } from 'zod';
import { localAnalysisResultSchema } from '../../contracts/analysis';

export const repositorySchema = z.object({ repository_id: z.string(), snapshot_id: z.string(), name: z.string(),
  source_kind: z.enum(['local', 'github']), github_url: z.string().nullable(), commit_sha: z.string().nullable() });
export type LocalRepository = z.infer<typeof repositorySchema>;
export type Limits = { max_files: number; max_file_bytes: number; max_total_bytes: number };
export type Job = { job_id: string; status: string; error_code: string | null; analysis_id: string | null };
export const limitsSchema = z.object({ max_files: z.number(), max_file_bytes: z.number(), max_total_bytes: z.number() });
let csrf = '';

export async function request(path: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch(`/api/local/${path}`, { signal, credentials: 'same-origin',
    ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.message === 'string' ? data.message : typeof data.detail === 'string' ? data.detail : 'The request could not be completed.');
  return data;
}

export async function startSession(): Promise<Limits> {
  const session = z.object({ csrf_token: z.string(), limits: limitsSchema }).parse(await request('session'));
  csrf = session.csrf_token;
  return session.limits;
}
export function query(repo: LocalRepository) {
  return new URLSearchParams({ repository_id: repo.repository_id, snapshot_id: repo.snapshot_id }).toString();
}
export async function loadReport(repo: LocalRepository, signal?: AbortSignal) {
  const result = await request(`report?${query(repo)}`, undefined, signal);
  if (!result) return null;
  if (result.repository_id !== repo.repository_id || result.snapshot_id !== repo.snapshot_id) throw new Error('Report belongs to a different source snapshot.');
  return localAnalysisResultSchema.parse(result.report);
}
export function shouldSkipPath(path: string) {
  const parts = path.toLowerCase().split('/');
  const name = parts.at(-1) ?? '';
  return parts.slice(0, -1).some(part => ['.git','node_modules','dist','build','vendor','.venv','venv','__pycache__','coverage','.idea','.next','.nuxt','target','bin','obj','.pytest_cache'].includes(part)) ||
    name === '.env' || name.startsWith('.env.') || ['id_rsa','id_ed25519','id_dsa','id_ecdsa','.npmrc','.pypirc','credentials','credentials.json'].includes(name) || /\.(pem|key|p12|pfx|keystore)$/.test(name);
}
export function validateFolderBudget(files: {size: number}[], limits: Limits) {
  if (files.length > limits.max_files || files.some(file => file.size > limits.max_file_bytes) || files.reduce((sum, file) => sum + file.size, 0) > limits.max_total_bytes) {
    throw new Error(`Folder exceeds the limits: ${limits.max_files} files, ${Math.floor(limits.max_file_bytes / 1024)} KiB per file, ${Math.floor(limits.max_total_bytes / 1024 / 1024)} MiB total. Choose a smaller source folder.`);
  }
}
export function sourceHref(repo: string, snapshot: string, path: string, line = 1) {
  return `/?${new URLSearchParams({ repo, snapshot, path, line: String(line) })}`;
}
