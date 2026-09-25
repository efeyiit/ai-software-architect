import { describe, expect, it } from 'vitest';
import { shouldSkipPath, sourceHref, validateFolderBudget } from '../../src/features/local/api';

describe('local workspace inputs', () => {
  it('filters generated and sensitive paths before reading file contents', () => {
    for (const path of ['.env', '.env.local', 'src/.env', 'node_modules/a.ts', '.git/config', 'cert.pem', 'id_rsa']) {
      expect(shouldSkipPath(path)).toBe(true);
    }
    expect(shouldSkipPath('src/main.py')).toBe(false);
  });
  it('checks byte and file limits before upload', () => {
    expect(() => validateFolderBudget([{size: 4}, {size: 2}], {max_files: 2, max_file_bytes: 4, max_total_bytes: 6})).not.toThrow();
    expect(() => validateFolderBudget([{size: 5}], {max_files: 2, max_file_bytes: 4, max_total_bytes: 6})).toThrow();
  });
  it('pins local source links to repository and snapshot', () => {
    const href = sourceHref('one', 'local:abc', 'src/a b.py', 3);
    expect(href).toContain('snapshot=local%3Aabc');
    expect(href).toContain('path=src%2Fa+b.py');
    expect(href).toContain('line=3');
  });
});
