import { z } from 'zod';
import { analysisResultSchema, parseAnalysisResult, sourceLocationSchema } from '../../contracts/analysis';

const snapshotSchema = z.strictObject({ repository_id: z.string().min(1), commit_sha: z.string().regex(/^[0-9a-f]{40}$/) });
const repositorySchema = z.strictObject({
  id: z.string().min(1), github_url: z.string().url(), name: z.string().min(1), branch: z.string().min(1),
  commit_sha: z.string().regex(/^[0-9a-f]{40}$/), languages: z.record(z.string(), z.number().int().nonnegative()),
  frameworks: z.array(z.string()),
});
const repositoryPathSchema = z.string().min(1).refine((path) => !path.startsWith('/') &&
  !path.includes('\\') && !/^[A-Za-z]:/.test(path) &&
  !path.split('/').some((part) => part === '' || part === '.' || part === '..') && !/[\x00-\x1f]/.test(path));
const fileSchema = z.strictObject({
  path: repositoryPathSchema, language: z.string().nullable(), included: z.boolean(), size: z.number().int().nonnegative(),
  exclusion_reason: z.string().nullable(),
});
const filesSchema = z.strictObject({ snapshot: snapshotSchema, files: z.array(fileSchema) });
const citationSchema = z.strictObject({ location: sourceLocationSchema, quote: z.string().nullable() });
const claimSchema = z.strictObject({ text: z.string().min(1), origin: z.enum(['static', 'ai']), citations: z.array(citationSchema) });
const summarySchema = z.strictObject({
  snapshot: snapshotSchema, ai_status: z.enum(['unavailable', 'validated', 'rejected']), path: z.string().min(1),
  responsibility: z.string(), responsibility_citations: z.array(citationSchema), structural_facts: z.array(claimSchema),
  ai_claims: z.array(claimSchema), uncertainties: z.array(z.string()),
});
const issuesSchema = z.strictObject({ analysis_id: z.string().min(1), status: z.string(), commit_sha: z.string(), findings: z.array(z.unknown()) });
const jobSchema = z.strictObject({ job_id: z.string(), status: z.string(), commit_sha: z.string(), attempts: z.number(),
  error_code: z.string().nullable(), analysis_id: z.string().nullable() });
const diagramBundleSchema = z.strictObject({ class_diagram: z.string(), sequence_diagram: z.string(), component_diagram: z.string() });
const diagramsSchema = z.strictObject({ snapshot: snapshotSchema, status: z.enum(['pending', 'running', 'succeeded', 'failed', 'partial', 'cancelled']), diagrams: z.strictObject({
  mermaid: diagramBundleSchema, plantuml: diagramBundleSchema,
}) });

export type RepositoryInfo = z.infer<typeof repositorySchema>;
export type RepositoryFile = z.infer<typeof fileSchema>;
export type RepositoryFiles = z.infer<typeof filesSchema>;
export type FileSummary = z.infer<typeof summarySchema>;
export type AnalysisResultData = z.infer<typeof analysisResultSchema>;
export type AnalysisJob = z.infer<typeof jobSchema>;
export type RepositoryDiagrams = z.infer<typeof diagramsSchema>;
export type ApiErrorKind = 'unauthorized' | 'unavailable' | 'not_found' | 'conflict' | 'failed';

export class ApiError extends Error {
  constructor(readonly kind: ApiErrorKind, message: string, readonly status?: number, readonly code?: string) {
    super(message);
    this.name = 'ApiError';
  }
}

function bodyCode(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail !== null && 'code' in detail && typeof detail.code === 'string') return detail.code;
  return undefined;
}

function classify(status: number, code?: string): ApiErrorKind {
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 404 && (code === 'analysis_unavailable' || code === 'file_unavailable' || code === 'repository_unavailable')) return 'not_found';
  if (status === 404) return 'unavailable';
  if (status === 422) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 502 || status === 503 || status === 504 || status === 429) return 'unavailable';
  return 'failed';
}

export class AriadneApi {
  private async request<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      response = await fetch(path, { ...init, credentials: 'include', headers: init.headers });
    } catch {
      throw new ApiError('unavailable', 'Ariadne API could not be reached.');
    }
    let body: unknown;
    try { body = await response.json(); } catch { body = undefined; }
    if (!response.ok) {
      const code = bodyCode(body);
      throw new ApiError(classify(response.status, code), code ?? `HTTP ${response.status}`, response.status, code);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) throw new ApiError('failed', 'The API response did not match the Ariadne contract.');
    return parsed.data;
  }

  getRepository(id: string): Promise<RepositoryInfo> {
    return this.request(`/api/repositories/${encodeURIComponent(id)}`, repositorySchema);
  }

  getFiles(id: string): Promise<RepositoryFiles> {
    return this.request(`/api/repositories/${encodeURIComponent(id)}/files`, filesSchema);
  }

  getFileSummary(id: string, path: string): Promise<FileSummary> {
    const query = new URLSearchParams({ path });
    return this.request(`/api/repositories/${encodeURIComponent(id)}/files/summary?${query}`, summarySchema);
  }

  async getLatestAnalysis(id: string): Promise<AnalysisResultData | null> {
    let latest: z.infer<typeof issuesSchema>;
    try {
      latest = await this.request(`/api/repositories/${encodeURIComponent(id)}/issues`, issuesSchema);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404 && error.code === 'analysis_unavailable') return null;
      throw error;
    }
    const result = await this.request(`/api/repositories/${encodeURIComponent(id)}/analyses/${encodeURIComponent(latest.analysis_id)}`, analysisResultSchema);
    return parseAnalysisResult(result);
  }

  getDiagrams(id: string): Promise<RepositoryDiagrams> {
    return this.request(`/api/repositories/${encodeURIComponent(id)}/diagrams`, diagramsSchema);
  }

  private async csrfToken(): Promise<string> {
    const session = await this.request('/auth/me', z.strictObject({ user_id: z.string(), csrf_token: z.string().min(1) }));
    return session.csrf_token;
  }

  async startAnalysis(id: string): Promise<{ status: string; job_id?: string; analysis_id?: string; commit_sha: string }> {
    const csrf = await this.csrfToken();
    return this.request(`/api/repositories/${encodeURIComponent(id)}/analyze`,
      z.strictObject({ status: z.string(), job_id: z.string().optional(), analysis_id: z.string().optional(), commit_sha: z.string() }),
      { method: 'POST', headers: { 'X-Ariadne-CSRF': csrf } });
  }

  getJob(id: string, jobId: string): Promise<AnalysisJob> {
    return this.request(`/api/repositories/${encodeURIComponent(id)}/jobs/${encodeURIComponent(jobId)}`, jobSchema);
  }

  getAnalysis(id: string, analysisId: string): Promise<AnalysisResultData> {
    return this.request(`/api/repositories/${encodeURIComponent(id)}/analyses/${encodeURIComponent(analysisId)}`, analysisResultSchema);
  }
}
