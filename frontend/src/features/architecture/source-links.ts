import type { RepositoryInfo } from '../overview/api';

export function sourceHref(repository: RepositoryInfo, path: string, line: number) {
  try {
    if (!path || path.startsWith('/') || path.includes('\\') || path.split('/').some((part) => !part || part === '.' || part === '..') || !Number.isInteger(line) || line < 1) return null;
    const base = new URL(repository.github_url);
    if (base.protocol !== 'https:' || base.hostname !== 'github.com' || !/^[0-9a-f]{40}$/.test(repository.commit_sha)) return null;
    const encodedPath = path.split('/').map(encodeURIComponent).join('/');
    return `${base.origin}${base.pathname.replace(/\/$/, '')}/blob/${repository.commit_sha}/${encodedPath}#L${line}`;
  } catch { return null; }
}
