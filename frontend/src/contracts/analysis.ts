import { z } from 'zod';

const strict = <T extends z.ZodRawShape>(shape: T) => z.strictObject(shape);

export const repositorySnapshotSchema = strict({
  repository_id: z.string().min(1),
  commit_sha: z.string().regex(/^[0-9a-f]{40}$/),
});

export const sourceLocationSchema = strict({
  path: z.string().min(1).refine((path) =>
    !path.startsWith('/') &&
    !path.includes('\\') &&
    !/^[A-Za-z]:/.test(path) &&
    !path.split('/').some((part) => part === '' || part === '.' || part === '..') &&
    !/[\x00-\x1f]/.test(path),
  ),
  start_line: z.number().int().positive(),
  end_line: z.number().int().positive(),
}).refine((location) => location.end_line >= location.start_line);

export const analysisFindingSchema = strict({
  id: z.string().min(1),
  source: z.enum(['static', 'ai']),
  issue_type: z.string().min(1),
  severity: z.enum(['info', 'low', 'medium', 'high', 'critical']),
  location: sourceLocationSchema,
  description: z.string().min(1),
  suggestion: z.string().nullable(),
});

export const analysisErrorSchema = strict({
  code: z.string().regex(/^[A-Z][A-Z0-9_]*$/),
  message: z.string().min(1),
  retryable: z.boolean(),
  location: sourceLocationSchema.nullable(),
});

export const analysisResultSchema = strict({
  schema_version: z.literal(1),
  analysis_id: z.string().min(1),
  snapshot: repositorySnapshotSchema,
  status: z.enum(['pending', 'running', 'succeeded', 'failed']),
  findings: z.array(analysisFindingSchema),
  errors: z.array(analysisErrorSchema),
}).superRefine((result, context) => {
  if (result.status === 'failed' && result.errors.length === 0) {
    context.addIssue({ code: 'custom', message: 'failed analysis requires at least one error' });
  }
  if (result.status === 'succeeded' && result.errors.length > 0) {
    context.addIssue({ code: 'custom', message: 'succeeded analysis cannot contain errors' });
  }
  if (new Set(result.findings.map((item) => item.id)).size !== result.findings.length) {
    context.addIssue({ code: 'custom', message: 'finding ids must be unique within an analysis' });
  }
});

export type AnalysisResult = z.infer<typeof analysisResultSchema>;

export function parseAnalysisResult(input: unknown): AnalysisResult {
  return analysisResultSchema.parse(input);
}
