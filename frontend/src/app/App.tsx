import { ThreadMark } from '../components/shell/ThreadMark';
import { ThemeToggle } from '../components/shell/ThemeToggle';
import { OverviewPage } from '../features/overview/OverviewPage';
import { FilesPage } from '../features/files/FilesPage';
import { ArchitecturePage } from '../features/architecture/ArchitecturePage';
import { FindingsPage } from '../features/findings/FindingsPage';
import { SecurityPage } from '../features/security/SecurityPage';
import { TestingPage } from '../features/testing/TestingPage';
import { DocumentationPage } from '../features/documentation/DocumentationPage';
import { DemoModeProvider } from '../features/demo/DemoMode';
import { AuthSessionProvider, useAuthSession } from '../features/auth/AuthSession';
import { LoginPage } from '../features/auth/LoginPage';
import { RepositoriesPage } from '../features/repositories/RepositoriesPage';

type Page = 'login' | 'dashboard' | 'repository' | 'not-found';
type RepositoryView = 'overview' | 'files' | 'architecture' | 'dependencies' | 'findings' | 'security' | 'testing' | 'documentation';

export function resolveRoute(pathname: string): { page: Page; repositoryId?: string; repositoryView?: RepositoryView } {
  if (pathname === '/' || pathname === '/login') return { page: 'login' };
  if (pathname === '/dashboard') return { page: 'dashboard' };
  const match = pathname.match(/^\/repository\/([^/]+)(?:\/(files|architecture|dependencies|findings|security|testing|documentation))?\/?$/);
  if (match) {
    try { return { page: 'repository', repositoryId: decodeURIComponent(match[1]), repositoryView: (match[2] as RepositoryView | undefined) ?? 'overview' }; }
    catch { return { page: 'not-found' }; }
  }
  return { page: 'not-found' };
}

const primaryLinks = [
  { href: '/dashboard', label: 'Dashboard', icon: 'grid' },
  { href: '/dashboard#repositories', label: 'Repositories', icon: 'layers' },
];

function routeHref(path: string) { return path; }

function Icon({ name }: { name: string }) {
  if (name === 'grid') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></svg>;
  if (name === 'layers') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></svg>;
  if (name === 'demo') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2Z"/><path d="m19 2 .8 2.2L22 5l-2.2.8L19 8l-.8-2.2L16 5l2.2-.8L19 2Z"/></svg>;
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v18M3 12h18"/></svg>;
}

function Brand() { return <a className="brand" href="/dashboard" aria-label="Ariadne home"><img className="brand-symbol" src="/brand/02-iplik.png" alt="" draggable="false"/><span>Ariadne</span></a>; }

function Navigation({ pathname, mobile = false }: { pathname: string; mobile?: boolean }) {
  const repositoryMatch = pathname.match(/^\/repository\/([^/]+)(?:\/(files|architecture|dependencies|findings|security|testing|documentation))?\/?$/);
  if (repositoryMatch) {
    const repositoryId = repositoryMatch[1];
    const base = `/repository/${repositoryId}`;
    const overviewActive = pathname === base || pathname === `${base}/`;
    const filesActive = pathname === `${base}/files` || pathname === `${base}/files/`;
    const architectureActive = pathname === `${base}/architecture` || pathname === `${base}/architecture/`;
    const dependenciesActive = pathname === `${base}/dependencies` || pathname === `${base}/dependencies/`;
    const findingsActive = pathname === `${base}/findings` || pathname === `${base}/findings/`;
    const securityActive = pathname === `${base}/security` || pathname === `${base}/security/`;
    const testingActive = pathname === `${base}/testing` || pathname === `${base}/testing/`;
    const documentationActive = pathname === `${base}/documentation` || pathname === `${base}/documentation/`;
    return <nav aria-label={mobile ? 'Mobile navigation' : 'Main navigation'} className="nav-list">
      <p className="nav-caption">REPOSITORY</p>
      <a className={`nav-link${overviewActive ? ' is-active' : ''}`} href={routeHref(base)} aria-current={overviewActive ? 'page' : undefined}><Icon name="grid"/><span>Overview</span></a>
      <a className={`nav-link${filesActive ? ' is-active' : ''}`} href={routeHref(`${base}/files`)} aria-current={filesActive ? 'page' : undefined}><Icon name="layers"/><span>Files</span></a>
      <a className={`nav-link${architectureActive ? ' is-active' : ''}`} href={routeHref(`${base}/architecture`)} aria-current={architectureActive ? 'page' : undefined}><Icon name="layers"/><span>Architecture</span></a>
      <a className={`nav-link${dependenciesActive ? ' is-active' : ''}`} href={routeHref(`${base}/dependencies`)} aria-current={dependenciesActive ? 'page' : undefined}><Icon name="layers"/><span>Dependencies</span></a>
      <a className={`nav-link${findingsActive ? ' is-active' : ''}`} href={routeHref(`${base}/findings`)} aria-current={findingsActive ? 'page' : undefined}><Icon name="layers"/><span>Findings</span></a>
      <a className={`nav-link${securityActive ? ' is-active' : ''}`} href={routeHref(`${base}/security`)} aria-current={securityActive ? 'page' : undefined}><Icon name="layers"/><span>Security</span></a>
      <a className={`nav-link${testingActive ? ' is-active' : ''}`} href={routeHref(`${base}/testing`)} aria-current={testingActive ? 'page' : undefined}><Icon name="layers"/><span>Testing</span></a>
      <a className={`nav-link${documentationActive ? ' is-active' : ''}`} href={routeHref(`${base}/documentation`)} aria-current={documentationActive ? 'page' : undefined}><Icon name="layers"/><span>Documentation</span></a>
      <a className="nav-link" href="/dashboard"><Icon name="grid"/><span>Workspace</span></a>
    </nav>;
  }
  return <nav aria-label={mobile ? 'Mobile navigation' : 'Main navigation'} className="nav-list">
    <p className="nav-caption">WORKSPACE</p>
    {primaryLinks.map((link) => {
      const active = link.href === '/dashboard' ? pathname === '/dashboard' : link.href.includes('#repositories') ? pathname === '/dashboard' : pathname.startsWith('/repository/');
      return <a className={`nav-link${active ? ' is-active' : ''}`} href={link.href} key={link.href} aria-current={active ? 'page' : undefined}>
        <Icon name={link.icon}/><span>{link.label}</span>
      </a>;
    })}
  </nav>;
}

function Sidebar({ pathname }: { pathname: string }) { return <aside className="sidebar"><Brand/><Navigation pathname={pathname}/><div className="sidebar-note"><span className="status-dot"/><span>Workspace connected<br/><small>Repository access is account scoped</small></span></div></aside>; }

function repositoryCrumb(pathname: string) {
  const route = pathname.match(/^\/repository\/[^/]+\/(files|architecture|dependencies|findings|security|testing|documentation)\/?$/)?.[1];
  if (!route) return pathname.startsWith('/repository/') ? 'Repository' : 'Overview';
  return route[0].toUpperCase() + route.slice(1);
}

function Topbar({ pathname }: { pathname: string }) {
  const auth = useAuthSession();
  return <header className="topbar">
    <details className="mobile-menu"><summary aria-label="Toggle navigation"><span/><span/><span/></summary><div className="mobile-menu-panel"><Brand/><Navigation pathname={pathname} mobile/></div></details>
    <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>{repositoryCrumb(pathname)}</strong></div>
    <div className="topbar-actions">{auth.state.status === 'signed-in' && <><button className="subtle-button" type="button" onClick={() => void auth.logout()} disabled={auth.loggingOut}>{auth.loggingOut ? 'Signing out…' : 'Sign out'}</button>{auth.logoutError && <span role="alert">{auth.logoutError}</span>}</>}<ThemeToggle/></div>
  </header>;
}

function PageHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="page-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>;
}

function NotFound() {
  return <section className="not-found"><span className="section-kicker">PAGE NOT FOUND</span><h1>We couldn’t find that page.</h1><p>Check the address or head back to your workspace.</p><a className="primary-button" href="/dashboard">Go to dashboard</a></section>;
}

function routeContent(route: ReturnType<typeof resolveRoute>) {
  if (route.page !== 'repository') return <NotFound/>;
  const repositoryId = route.repositoryId ?? '';
  if (route.repositoryView === 'files') return <FilesPage repositoryId={repositoryId}/>;
  if (route.repositoryView === 'architecture' || route.repositoryView === 'dependencies') return <ArchitecturePage repositoryId={repositoryId} view={route.repositoryView}/>;
  if (route.repositoryView === 'findings') return <FindingsPage repositoryId={repositoryId}/>;
  if (route.repositoryView === 'security') return <SecurityPage repositoryId={repositoryId}/>;
  if (route.repositoryView === 'testing') return <TestingPage repositoryId={repositoryId}/>;
  if (route.repositoryView === 'documentation') return <DocumentationPage repositoryId={repositoryId}/>;
  return <OverviewPage repositoryId={repositoryId}/>;
}

function AppBody({ pathname, route }: { pathname: string; route: ReturnType<typeof resolveRoute> }) {
  const auth = useAuthSession();
  if (auth.state.status === 'loading') return <section className="feature-loading" role="status" aria-busy="true"><span className="loading-orbit"/>Checking your session…</section>;
  if (auth.state.status !== 'signed-in') return <LoginPage state={auth.state} retry={auth.retry} required={route.page !== 'login'}/>;
  if (route.page === 'login' || route.page === 'dashboard') route = { page: 'dashboard' };
  if (route.page === 'not-found') return <NotFound/>;
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <Sidebar pathname={pathname}/>
    <div className="main-column">
      <Topbar pathname={pathname}/>
      <main id="main-content" className="page-content" tabIndex={-1}>{route.page === 'dashboard' ? <RepositoriesPage session={auth.state.session}/> : routeContent(route)}</main>
      <footer className="app-footer"><span>Ariadne</span><span>Understand the systems behind your code.</span></footer>
    </div>
  </div>;
}

export function App({ pathname: suppliedPathname }: { pathname?: string } = {}) {
  const pathname = suppliedPathname ?? (typeof window === 'undefined' ? '/' : window.location.pathname);
  const route = resolveRoute(pathname);
  return <DemoModeProvider><AuthSessionProvider><AppBody pathname={pathname} route={route}/></AuthSessionProvider></DemoModeProvider>;
}
