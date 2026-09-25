import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, AriadneApi, type RepositoryDiagrams } from '../../src/features/overview/api';
import { assertCurrentDiagramSnapshot } from '../../src/features/architecture/ArchitecturePage';
import { sourceHref } from '../../src/features/architecture/source-links';
import type { RepositoryInfo } from '../../src/features/overview/api';

const sha = 'a'.repeat(40);
const diagramResponse = {
  snapshot: { repository_id: 'repo-42', commit_sha: sha }, status: 'succeeded',
  diagrams: {
    mermaid: { class_diagram: 'classDiagram', sequence_diagram: 'sequenceDiagram', component_diagram: 'flowchart LR' },
    plantuml: { class_diagram: '@startuml class', sequence_diagram: '@startuml sequence', component_diagram: '@startuml component' },
  },
};

afterEach(() => vi.unstubAllGlobals());

describe('T18 diagram API utility', () => {
  it('loads both real diagram formats with the shared same-origin session request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => diagramResponse });
    vi.stubGlobal('fetch', fetchMock);

    const result = await new AriadneApi().getDiagrams('repo/42');

    expect(result.diagrams.mermaid.component_diagram).toBe('flowchart LR');
    expect(result.diagrams.plantuml.sequence_diagram).toBe('@startuml sequence');
    expect(fetchMock).toHaveBeenCalledWith('/api/repositories/repo%2F42/diagrams', expect.objectContaining({ credentials: 'include' }));
  });

  it('rejects unexpected T18 output fields and status values', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...diagramResponse, status: 'guess', unsafe: '<script>' }) }));

    await expect(new AriadneApi().getDiagrams('repo-42')).rejects.toMatchObject({ kind: 'failed' });
  });

  it('rejects diagram bundles from a different repository snapshot', () => {
    expect(() => assertCurrentDiagramSnapshot(diagramResponse as RepositoryDiagrams, 'repo-42', sha, sha)).not.toThrow();
    expect(() => assertCurrentDiagramSnapshot(diagramResponse as RepositoryDiagrams, 'another-repo', sha, sha))
      .toThrowError(ApiError);
    expect(() => assertCurrentDiagramSnapshot(diagramResponse as RepositoryDiagrams, 'repo-42', 'b'.repeat(40), sha))
      .toThrowError(ApiError);
  });
});

describe('source links', () => {
  const repository = {
    id: 'repo-42', github_url: 'https://github.com/example/repo', name: 'repo', branch: 'main', commit_sha: sha,
    languages: {}, frameworks: [],
  } satisfies RepositoryInfo;

  it('targets the analyzed commit and source line while encoding path segments', () => {
    expect(sourceHref(repository, 'src/My File.tsx', 12)).toBe(`https://github.com/example/repo/blob/${sha}/src/My%20File.tsx#L12`);
  });

  it('refuses unsafe or non-GitHub source URLs', () => {
    expect(sourceHref(repository, '../secret.ts', 1)).toBeNull();
    expect(sourceHref({ ...repository, github_url: 'javascript:alert(1)' }, 'src/file.ts', 1)).toBeNull();
  });
});
