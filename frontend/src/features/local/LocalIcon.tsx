import type { CSSProperties } from 'react';

type IconName = 'play' | 'pause' | 'github' | 'folder' | 'branch' | 'arrow' | 'search' | 'grid' | 'upload' | 'spark' | 'monitor';
const paths: Record<IconName, string> = {
  play: 'm8 5 11 7-11 7Z',
  pause: 'M8 5v14M16 5v14',
  github: 'M12 .75a11.25 11.25 0 0 0-3.56 21.92c.56.1.77-.24.77-.54v-2.1c-3.13.68-3.79-1.33-3.79-1.33-.51-1.3-1.25-1.65-1.25-1.65-1.02-.7.08-.68.08-.68 1.13.08 1.72 1.16 1.72 1.16 1 1.71 2.63 1.22 3.27.93.1-.72.39-1.22.71-1.5-2.5-.28-5.13-1.25-5.13-5.56 0-1.23.44-2.23 1.16-3.02-.12-.29-.5-1.43.11-2.98 0 0 .95-.3 3.1 1.16a10.8 10.8 0 0 1 5.63 0c2.15-1.46 3.09-1.16 3.09-1.16.62 1.55.23 2.69.12 2.98.72.79 1.16 1.79 1.16 3.02 0 4.32-2.63 5.28-5.14 5.55.4.35.76 1.03.76 2.09v3.09c0 .3.2.65.77.54A11.25 11.25 0 0 0 12 .75Z',
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
  return <svg className={`local-icon ${className}`} viewBox="0 0 24 24" fill={name === 'github' ? 'currentColor' : 'none'} stroke={name === 'github' ? 'none' : 'currentColor'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}
export function revealStyle(index: number): CSSProperties { return {'--reveal-delay': `${Math.min(index, 5) * 35}ms`} as CSSProperties; }
