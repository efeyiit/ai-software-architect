import { z } from 'zod';

const shaSchema = z.string().regex(/^[0-9a-f]{40}$/);
const pathSchema = z.string().min(1).refine((path) => !path.startsWith('/') && !path.includes('\\') &&
  !/^[A-Za-z]:/.test(path) && !path.split('/').some((part) => !part || part === '.' || part === '..') && !/[\x00-\x1f]/.test(path));
const citationSchema = z.strictObject({ path: pathSchema, start_line: z.number().int().positive(), end_line: z.number().int().positive(),
  commit_sha: shaSchema, quote: z.string() }).refine((citation) => citation.end_line >= citation.start_line);
const claimSchema = z.strictObject({ text: z.string(), citations: z.array(citationSchema) });
const metaSchema = z.strictObject({ mode: z.literal('local_demo'), label: z.literal('Yerel demo'), repository_id: z.string().min(1),
  commit_sha: shaSchema, data_origin: z.literal('bundled_synthetic'), model_status: z.enum(['ready', 'loading', 'unavailable']) });
const responseSchema = z.strictObject({ status: z.enum(['answered', 'no_evidence', 'unavailable', 'rejected']), answer: z.string(),
  origin: z.enum(['ai', 'none']), claims: z.array(claimSchema), commit_sha: shaSchema }).superRefine((response, context) => {
    if ((response.status === 'answered') !== (response.origin === 'ai')) context.addIssue({ code: 'custom', message: 'answer origin does not match response status' });
  });

export type LocalDemoMeta = z.infer<typeof metaSchema>;
export type LocalDemoResponse = z.infer<typeof responseSchema>;
export const MAX_QUESTION_LENGTH = 1000;

export class DemoApiError extends Error {
  constructor(message: string, readonly retryable: boolean) { super(message); this.name = 'DemoApiError'; }
}

function ensureLoopbackDemo() {
  if (typeof window === 'undefined' || !['127.0.0.1', 'localhost'].includes(window.location.hostname) || window.location.port !== '8765')
    throw new DemoApiError('Yerel demoyu 127.0.0.1:8765 adresinde açın. Bu ekran ağ üzerindeki veya canlı bir servise bağlanmaz.', false);
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  ensureLoopbackDemo();
  let response: Response;
  try { response = await fetch(path, { ...init, credentials: 'omit', headers: init?.body ? { 'Content-Type': 'application/json' } : undefined }); }
  catch { throw new DemoApiError('Yerel demo servisine ulaşılamadı. Uygulama başlatılmış mı?', true); }
  if (!response.ok) throw new DemoApiError(response.status >= 500 ? 'Yerel model veya demo servisi şu anda yanıt veremiyor.' : 'Yerel demo isteği reddedildi.', response.status >= 500 || response.status === 429);
  let raw: unknown;
  try { raw = await response.json(); } catch { throw new DemoApiError('Demo servisi geçersiz bir yanıt döndürdü.', true); }
  const parsed = schema.safeParse(raw);
  if (!parsed.success) throw new DemoApiError('Demo yanıtı beklenen yerel API sözleşmesine uymuyor.', false);
  return parsed.data;
}

export const localDemoApi = {
  getMeta: () => request('/demo/meta', metaSchema),
  ask: (question: string) => request('/demo/chat', responseSchema, { method: 'POST', body: JSON.stringify({ question }) }),
};

export function parseDemoMeta(input: unknown) { return metaSchema.parse(input); }
export function parseDemoResponse(input: unknown) { return responseSchema.parse(input); }

export function citationsForCommit(response: LocalDemoResponse, expectedSha: string) {
  return response.claims.flatMap((claim) => claim.citations).filter((citation) => citation.commit_sha === expectedSha && citation.commit_sha === response.commit_sha);
}
