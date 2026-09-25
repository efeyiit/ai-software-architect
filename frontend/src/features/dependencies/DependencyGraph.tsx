import { useState } from 'react';
import type { AnalysisResultData, RepositoryInfo } from '../overview/api';
import { sourceHref } from '../architecture/source-links';
import '../architecture/architecture.css';

type DependencyData = NonNullable<Extract<AnalysisResultData, { schema_version: 2 }>['dependencies']>;
type DependencyNode = DependencyData['nodes'][number];

function NodeButton({ node, selected, onSelect }: { node: DependencyNode; selected: boolean; onSelect: (id: string) => void }) {
  return <button className={`dependency-node${selected ? ' is-selected' : ''}`} type="button" aria-pressed={selected}
    aria-label={`${node.name} ${node.kind} source node`} onClick={() => onSelect(node.id)}>
    <span className="dependency-node-kind">{node.kind}</span><strong>{node.name}</strong><code>{node.location.path}:{node.location.start_line}</code>
  </button>;
}

function SourceLink({ repository, node }: { repository: RepositoryInfo; node: DependencyNode }) {
  const href = sourceHref(repository, node.location.path, node.location.start_line);
  return href ? <a className="architecture-source-link" href={href} target="_blank" rel="noopener noreferrer">Open {node.location.path}:{node.location.start_line} at analyzed commit</a>
    : <span className="architecture-source-link">{node.location.path}:{node.location.start_line}</span>;
}

export function DependencyGraph({ graph, repository }: { graph: DependencyData; repository: RepositoryInfo }) {
  if (!graph.nodes.length && !graph.edges.length) return <div className="feature-notice"><span className="notice-mark" aria-hidden="true">i</span><div><strong>No dependencies in this snapshot</strong><p>The report returned an empty dependency graph.</p></div></div>;
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedNode = selectedId ? nodes.get(selectedId) ?? null : null;
  return <>
    <div className="dependency-summary"><span><strong>{graph.nodes.length}</strong> source nodes</span><span><strong>{graph.edges.length}</strong> relationships</span><span><strong>{graph.cycles.length}</strong> cycles</span></div>
    <section className="dependency-selection" aria-live="polite" aria-atomic="true">
      {selectedNode ? <><span className="section-kicker">SELECTED SOURCE NODE</span><strong>{selectedNode.name}</strong><span>{selectedNode.kind} · {selectedNode.language} · {selectedNode.location.path}:{selectedNode.location.start_line}</span><SourceLink repository={repository} node={selectedNode}/></>
        : <span>Select a graph node to inspect and open its source.</span>}
    </section>
    {graph.critical_nodes.length > 0 && <section className="dependency-critical" aria-labelledby="critical-title"><h3 id="critical-title">Critical nodes</h3><div className="dependency-node-list">{graph.critical_nodes.map((id) => nodes.get(id)).filter((node): node is DependencyNode => Boolean(node)).map((node) => <NodeButton key={node.id} node={node} selected={selectedId === node.id} onSelect={setSelectedId}/>)}</div></section>}
    {graph.nodes.length > 0 && <section className="dependency-graph-section" aria-labelledby="nodes-title"><div className="architecture-section-heading"><h3 id="nodes-title">Graph nodes</h3><span>Open a node’s source at this commit</span></div>
      <div className="dependency-node-list">{graph.nodes.map((node) => <NodeButton key={node.id} node={node} selected={selectedId === node.id} onSelect={setSelectedId}/>)}</div></section>}
    <section className="dependency-edges" aria-labelledby="edges-title"><div className="architecture-section-heading"><h3 id="edges-title">Relationships</h3><span>Resolved, ambiguous, and external edges are labeled</span></div>
      {graph.edges.length ? <ul>{graph.edges.map((edge, index) => {
        const source = nodes.get(edge.source); const target = edge.target ? nodes.get(edge.target) : null;
        return <li className={`dependency-edge edge-${edge.status}`} key={`${edge.source}:${edge.expression}:${index}`}>
          <div className="dependency-edge-route">{source ? <NodeButton node={source} selected={selectedId === source.id} onSelect={setSelectedId}/> : <span className="dependency-endpoint">Unknown source · {edge.source}</span>}
            <span className="dependency-arrow" aria-hidden="true">→</span>
            {target ? <NodeButton node={target} selected={selectedId === target.id} onSelect={setSelectedId}/> : <span className="dependency-endpoint">{edge.status === 'external' ? 'External target' : 'Unresolved target'}</span>}</div>
          <div className="dependency-edge-meta"><span className={`edge-status status-${edge.status}`}>{edge.status}</span><span>{edge.kind}</span><code>{edge.expression}</code>
            {edge.candidates.length > 0 && <span>Candidates: {edge.candidates.map((id) => nodes.get(id)?.name ?? id).join(', ')}</span>}{edge.reason && <span>{edge.reason}</span>}
            <a className="architecture-source-link" href={sourceHref(repository, edge.location.path, edge.location.start_line) ?? undefined} target="_blank" rel="noopener noreferrer">{edge.location.path}:{edge.location.start_line}</a></div>
        </li>;
      })}</ul> : <p className="architecture-muted">No dependency relationships were returned.</p>}
    </section>
    {graph.cycles.length > 0 && <section className="dependency-cycles" aria-labelledby="cycles-title"><h3 id="cycles-title">Circular dependencies</h3><ul>{graph.cycles.map((cycle, index) => <li key={`${cycle.join('|')}:${index}`}>
      {cycle.map((id, nodeIndex) => { const node = nodes.get(id); return <span key={`${id}:${nodeIndex}`}>{node ? <NodeButton node={node} selected={selectedId === node.id} onSelect={setSelectedId}/> : <code>{id}</code>}{nodeIndex < cycle.length - 1 && <span className="cycle-arrow" aria-hidden="true">↻</span>}</span>; })}
    </li>)}</ul></section>}
  </>;
}
