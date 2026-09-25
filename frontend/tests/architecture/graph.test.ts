import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DependencyGraph } from '../../src/features/dependencies/DependencyGraph';
import type { RepositoryInfo } from '../../src/features/overview/api';

const repository: RepositoryInfo = {
  id: 'repo-42', github_url: 'https://github.com/example/repo', name: 'repo', branch: 'main',
  commit_sha: 'a'.repeat(40), languages: {}, frameworks: [],
};

const graph = {
  nodes: [
    { id: 'a', kind: 'file' as const, language: 'typescript' as const, name: '<img src=x onerror=alert(1)>', location: { path: 'src/a.ts', start_line: 3, end_line: 8 } },
    { id: 'b', kind: 'file' as const, language: 'typescript' as const, name: 'B', location: { path: 'src/b.ts', start_line: 6, end_line: 12 } },
  ],
  edges: [
    { source: 'a', target: 'b', kind: 'import' as const, status: 'resolved' as const, expression: './b', location: { path: 'src/a.ts', start_line: 3, end_line: 3 }, candidates: [], reason: null },
    { source: 'a', target: null, kind: 'call' as const, status: 'ambiguous' as const, expression: 'choose()', location: { path: 'src/a.ts', start_line: 4, end_line: 4 }, candidates: ['b'], reason: 'Multiple candidates' },
    { source: 'b', target: null, kind: 'import' as const, status: 'external' as const, expression: 'react', location: { path: 'src/b.ts', start_line: 7, end_line: 7 }, candidates: [], reason: 'External package' },
  ],
  cycles: [['a', 'b']], critical_nodes: ['a'],
};

describe('dependency graph presentation', () => {
  it('links each node to its current commit and labels edge states and cycles', () => {
    const html = renderToStaticMarkup(createElement(DependencyGraph, { graph, repository }));

    expect(html).toContain('https://github.com/example/repo/blob/' + repository.commit_sha + '/src/a.ts#L3');
    expect(html).toContain('resolved');
    expect(html).toContain('ambiguous');
    expect(html).toContain('external');
    expect(html).toContain('Circular dependencies');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).not.toContain('<img src=x');
  });
});
