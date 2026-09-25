import type { CSSProperties } from 'react';

type IconName = 'folder' | 'branch' | 'arrow' | 'search' | 'grid' | 'upload' | 'spark' | 'monitor';
const paths: Record<IconName, string> = {
  folder: 'M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z',
  branch: 'M6 6v12M18 6v3a5 5 0 0 1-5 5H6M3 3h6v6H3ZM3 17h6v5H3ZM15 2h6v6h-6Z',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z',
  upload: 'M12 16V4m-5 5 5-5 5 5M4 15v5h16v-5',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',
  monitor: 'M3 4h18v13H3Zm5 17h8m-4-4v4',
};
export function LocalIcon({name, className = ''}: {name: IconName; className?: string}) {
  return <svg className={`local-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}
export function revealStyle(index: number): CSSProperties { return {'--reveal-delay': `${Math.min(index, 5) * 35}ms`} as CSSProperties; }
