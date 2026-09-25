import { useEffect } from 'react';

export function SourceText({ content, line = 1 }: { content: string; line?: number }) {
  useEffect(() => { document.getElementById(`source-line-${line}`)?.scrollIntoView({ block: 'center' }); }, [content, line]);
  return <pre className="local-source" tabIndex={0} aria-label="Source code"><code>{content.split('\n').map((text, index) =>
    <span key={index} id={`source-line-${index + 1}`} className={index + 1 === line ? 'is-highlighted' : ''}><span className="local-line-number" aria-hidden="true">{index + 1}</span>{text}{'\n'}</span>)}</code></pre>;
}
