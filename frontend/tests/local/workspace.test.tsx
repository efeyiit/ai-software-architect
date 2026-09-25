import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { SourceText } from '../../src/features/local/SourceText';
import { LocalReport } from '../../src/features/local/LocalReport';
import type { LocalAnalysisResult } from '../../src/contracts/analysis';
import type { LocalRepository } from '../../src/features/local/api';

it('matches security findings by merged report identity and withholds sensitive summaries', () => {
  const report = { items: [{ id: 'merged', roles: ['security'], finding: {id:'original'} }], findings: [{ id:'merged', severity:'high', source:'static', issue_type:'secret', description:'sensitive value', location:{path:'main.py',start_line:1} }] } as unknown as LocalAnalysisResult;
  const repo = {repository_id:'one',snapshot_id:'local:'+'a'.repeat(64)} as LocalRepository;
  const html = renderToStaticMarkup(<LocalReport report={report} repo={repo} view="Security"/>);
  expect(html).toContain('Potential security issue');
  expect(html).not.toContain('sensitive value');
});

it('renders source as inert text with addressable highlighted lines', () => {
  const html = renderToStaticMarkup(<SourceText content={'<script>alert(1)</script>\nprint(2)'} line={2}/>);
  expect(html).not.toContain('<script>');
  expect(html).toContain('&lt;script&gt;');
  expect(html).toContain('id="source-line-2"');
  expect(html).toContain('is-highlighted');
});
