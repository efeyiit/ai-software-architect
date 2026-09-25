import { describe, expect, it } from 'vitest';
import { citationsForCommit, MAX_QUESTION_LENGTH, parseDemoMeta, parseDemoResponse } from '../../src/features/demo/api';

const sha = '0123456789abcdef0123456789abcdef01234567';
const meta = { mode: 'local_demo', label: 'Yerel demo', repository_id: 'demo-commerce-api', commit_sha: sha, data_origin: 'bundled_synthetic', model_status: 'ready' };
const response = { status: 'answered', origin: 'ai', answer: 'The order flow starts here.', commit_sha: sha, claims: [{ text: 'Orders are created in this module.', citations: [{ path: 'src/api/orders.ts', start_line: 18, end_line: 21, commit_sha: sha, quote: 'createOrder()' }] }] };

describe('local demo contract', () => {
  it('accepts only the bundled loopback demo meta states', () => {
    expect(parseDemoMeta(meta).model_status).toBe('ready');
    expect(parseDemoMeta({ ...meta, model_status: 'loading' }).model_status).toBe('loading');
    expect(() => parseDemoMeta({ ...meta, data_origin: 'live_repository' })).toThrow();
  });
  it('caps one question at the backend 1000 character limit', () => {
    expect(MAX_QUESTION_LENGTH).toBe(1000);
  });
  it('rejects unsafe citations and a claimed AI answer without AI origin', () => {
    expect(() => parseDemoResponse({ ...response, claims: [{ text: 'bad', citations: [{ path: '../private', start_line: 1, end_line: 1, commit_sha: sha, quote: 'x' }] }] })).toThrow();
    expect(() => parseDemoResponse({ ...response, origin: 'none' })).toThrow();
  });
  it('returns only citations matching the active immutable fixture SHA', () => {
    const wrongSha = 'f'.repeat(40);
    const parsed = parseDemoResponse({ ...response, claims: [{ ...response.claims[0], citations: [...response.claims[0].citations, { ...response.claims[0].citations[0], commit_sha: wrongSha }] }] });
    expect(citationsForCommit(parsed, sha)).toHaveLength(1);
    expect(citationsForCommit(parsed, wrongSha)).toHaveLength(0);
  });
});
