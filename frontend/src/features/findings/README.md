# Findings, security, testing and documentation screens (T29)

The four repository routes are `/repository/:id/findings`, `/security`, `/testing`, and `/documentation`. They load the authenticated current repository and latest analysis using the shared strict `AriadneApi` contract. The report repository ID and 40-character commit SHA must match current repository metadata; otherwise the report is rejected as a changed snapshot. No screen creates replacement data when a report field is absent. Loading, empty report, request error, 401/403, unavailable API (including 503), retry, and partial analysis have distinct UI states. Live authentication is not assumed.

Findings can be filtered by severity and source type. Static evidence and AI interpretation use separate labels. Source links accept only normalized relative paths and `https://github.com` URLs and point at the analyzed immutable commit and source line. Refactoring recommendations remain labeled deterministic candidates.

Security findings are selected only from v2 merge items associated with the security role. Each is labeled a possible risk. The page omits finding descriptions, suggestions, code snippets, and secret values; it says that the value is withheld. A lack of returned signals is not represented as proof that a repository is secure.

Testing presents discovered test files, service candidates without linked test paths, and imported coverage data in separate panels. Discovery is not test execution, a service candidate is not a coverage measurement, and coverage is shown only when the report supplies a coverage artifact. Missing coverage remains “Not supplied” with the report's coverage status.

README/API output is explicitly draft content. Markdown and HTML are displayed only as escaped text in `<pre>`; the screen does not render repository-supplied markup. Source-backed facts and route evidence keep file/line references. Copy and download actions announce success or failure to users.

The existing shell owns navigation, logo, LL Circular font fallback and light/dark theme. Feature styles use shared theme variables, respond to narrow screens, retain keyboard focus outlines and avoid motion under `prefers-reduced-motion`. `?demo=fixture` in development marks controlled browser-intercepted responses; it never makes them live API or authentication evidence.

## Focused checks

From `frontend/`:

```text
pnpm exec vitest run tests/findings
pnpm test
pnpm build
```

T29 verification from `frontend/`: `pnpm exec vitest run tests/findings` passed **9 tests in 2 files**; `pnpm test` passed **48 tests in 10 files**; `pnpm build` passed TypeScript and Vite production build. Vite reports the existing dynamically loaded 662 kB diagram chunk warning.

Microsoft Edge browser checks used explicitly intercepted API responses. At desktop 1440×1000 and mobile 390×844, findings, security, testing and documentation screens were rendered across both light and dark themes. The security fixture contained a sentinel secret in its finding description; the security page did not display it. A malicious HTML-like README string appeared as inert text with no image element. Mobile document width matched viewport width. Copy announced success and download produced `README-draft.md`. Controlled 401 showed the sign-in state; controlled 503 showed unavailable and recovered after retry. These are UI fixtures only, not live API/authentication evidence. The default Chrome browser was unavailable, so Microsoft Edge was used.

Screenshots are saved under a local, unpublished visual-evidence directory: `findings-desktop-light.png`, `findings-desktop-dark.png`, `security-desktop-light.png`, `security-desktop-dark.png`, `testing-mobile-light.png`, and `documentation-mobile-dark.png`.
