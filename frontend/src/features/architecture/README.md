# Architecture and dependency screens (T28)

`/repository/:id/architecture` and `/repository/:id/dependencies` read repository metadata and the latest analysis through the shared `AriadneApi`. They require the report's repository ID and commit SHA to match the repository's current SHA before showing source links or diagrams. The dependency node, edge, evidence, and cycle records come from the v2 report; v1 reports and absent sections render explicit unavailable states.

Architecture evidence is shown as supported, mixed, or insufficient, with supporting evidence, contradictions, and uncertainty kept visible. The existing low/medium/high confidence field is presented as a limited/moderate/strong ordinal signal and explicitly labeled as not a probability.

Source references open the GitHub blob URL pinned to the analyzed 40-character commit and line. Only `https://github.com` repository URLs and normalized relative paths are accepted. API text is rendered by React as text; repository content is never interpreted as HTML or inserted with `innerHTML`.

The T18 diagram section calls `GET /api/repositories/{id}/diagrams` using the shared credentialed, strict-schema request utility. It verifies repository and commit SHA against both repository metadata and the displayed report. Mermaid 11.17.2 is dynamically imported only when the local preview is selected. Directives, comments, active links, and HTML labels are rejected; the returned SVG passes an element and attribute allowlist before it enters a scriptless, permissionless iframe with a restrictive content security policy. PlantUML remains source-only for local tools, and neither format is sent to a remote renderer. Mermaid and PlantUML class, sequence, and component sources can be viewed and downloaded. 401, 503, invalid response, and changed snapshot states remain visible; diagram retry is separate from report loading.

`?demo=fixture` in Vite development mode adds a controlled-API-fixture banner. Browser tests intercept API responses explicitly; this banner does not switch the application to synthetic report data. Live API runs never show that banner. The shell's logo, existing light/dark theme tokens and LL Circular font stack remain in use. Feature motion respects `prefers-reduced-motion`.

## Focused checks

From `frontend/`:

```text
pnpm exec vitest run tests/architecture
pnpm test
pnpm build
```

T28 verification: full frontend suite **39 passed across 8 files**; `pnpm build` passed its TypeScript check and Vite production build. Mermaid is the one added dependency, pinned to the version already used by the T18 diagram syntax checks. The local preview is dynamically imported, and the production build still reports one 662 kB dynamically loaded chunk (143 kB gzip) for diagram code.

Browser verification used Microsoft Edge with Playwright. At `http://127.0.0.1:5173/`, desktop `1440×1000` and mobile `390×844` exercised architecture/dependency navigation, dark and light themes, Mermaid class/sequence/component rendering in the sandbox, PlantUML source, an adversarial HTML-like node label, keyboard node selection and commit-pinned file navigation, reduced motion, narrow-screen overflow, empty and partial reports, the diagram `503` retry/recovery, and a separate intercepted `401` session state. The test captured no page, console, or framework errors. All report/diagram bodies came from explicit browser route interception; they are controlled fixtures, not live API or authentication proof. The `401` error route had no fixture banner, while fixture-driven report pages showed the persistent controlled-fixture banner.

Screenshots are saved under a local, unpublished visual-evidence directory:

- `desktop-light-architecture.png`
- `desktop-dark-architecture-plantuml.png`
- `desktop-dark-mermaid-class.png`
- `desktop-dark-dependencies.png`
- `mobile-dark-dependencies.png`
- `mobile-light-dependencies.png`
- `diagram-503-retry-state.png`
- `diagram-retry-recovered.png`
- `partial-report.png`
- `live-unauthorized.png`
