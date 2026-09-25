import { describe, expect, it } from 'vitest';
import { localSnapshotSchema, snapshotRevision } from '../../src/contracts/analysis';

describe('local snapshot identity', () => {
  it('keeps local content IDs separate from Git commits', () => {
    const wire = { repository_id: 'one', source_kind: 'local', commit_sha: null, snapshot_id: `local:${'a'.repeat(64)}` };
    expect(localSnapshotSchema.parse(wire)).toEqual(wire);
    expect(snapshotRevision(wire)).toBe(wire.snapshot_id);
    expect(localSnapshotSchema.safeParse({ ...wire, commit_sha: 'a'.repeat(40) }).success).toBe(false);
    expect(localSnapshotSchema.safeParse({ ...wire, snapshot_id: 'a'.repeat(40) }).success).toBe(false);
    expect(snapshotRevision({ repository_id: 'one', commit_sha: 'b'.repeat(40) })).toBe('b'.repeat(40));
  });
});
