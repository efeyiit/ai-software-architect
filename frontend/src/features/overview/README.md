# T27 — Repository overview and files

Repository routes are mounted inside the existing Ariadne shell:

- `/repository/:id` loads repository metadata, the current source-file inventory, and the newest analysis for the authorized current commit.
- `/repository/:id/files` shows the current snapshot tree. Selecting an included source file requests its summary; source bytes are never sent to the browser.

## API data and trust boundary

The feature reads the T25 endpoints:

- `GET /api/repositories/{id}` for name, branch, current commit SHA, language metadata, and framework hints.
- `GET /api/repositories/{id}/files` for normalized tree paths, language, size, inclusion, and exclusion reason. Counts on the overview come from `included` tree entries, not an estimate from language metadata.
- `GET /api/repositories/{id}/files/summary?path=...` for T17 deterministic facts and source locations. The response must match the selected repository, path, and current commit SHA before it renders.
- `GET /api/repositories/{id}/issues` followed by `GET /api/repositories/{id}/analyses/{analysis_id}` for the newest result. Findings, role states, errors, and partial status are shown as returned.
- User initiated `POST /api/repositories/{id}/analyze` obtains the session CSRF token from `GET /auth/me`, sends it in `X-Ariadne-CSRF`, and polls the owner-scoped job route. Cached, partial, failed, and cancelled results retain their actual states.

Requests use same-origin `credentials: 'include'`. No user identity header, fabricated report, file content, or client-side authorization value is sent. `401`/`403`, missing analysis, changed snapshot, missing API capability, and service errors remain distinct UI states with retry where safe. The backend rechecks ownership, GitHub permission, and current SHA on these reads.

The session uses an HTTPS-only `__Host-` Secure cookie. This local HTTP preview cannot perform real sign-in; the screen states that limit explicitly. A successful frontend fixture interaction is not evidence of real authentication or API integration.

## Browser fixture

For visual review only, open a development server at `/repository/demo-commerce-api?demo=fixture`. The page displays a persistent **TEST / DEMO FIXTURE** notice. The UI branch is guarded by Vite's development flag and the explicit `demo=fixture` query. However, the production build inspected for T27 emitted a separate `demo-fixture` JavaScript chunk (2.40 kB) containing fixture data. The fixture is therefore present and downloadable in the built assets, even though the production UI path is guarded. Do not describe the fixture bytes as excluded from the production bundle, and do not use fixture values as product data or live API evidence.

The supplied LL Circular/Circular Std stack remains in place with the existing Arial fallback; no licensed font file is bundled. Feature styles use the shell's light/dark theme tokens and suppress feature animation when `prefers-reduced-motion` is enabled.

## Verification

From `frontend/`:

```text
pnpm test
pnpm build
```

T27 verification result: `pnpm exec vitest run tests/overview tests/shell tests/contracts` passed (27 tests), and `pnpm build` completed its TypeScript check and production bundle. The checked production build emitted the fixture chunk described above. Browser QA used the installed Edge browser with Playwright. It exercised the development fixture at 1440×1000 and 390×844: light/dark theme, keyboard navigation to Files, keyboard selection of an included file, disabled excluded files, summary evidence, repository and inventory retry after unavailable responses, empty analysis, unauthorized rendering, and horizontal-overflow checks. The retry and error browser cases used explicit HTTP response interception; they did not connect to a live API or database. The local HTTP run did not prove real GitHub sign-in, Secure-cookie session issuance, or authenticated API access. Expected console resource failures were limited to the intentionally unproxied local API (`404`) and the intercepted `401`/`503` responses; no JavaScript runtime or framework errors appeared.

Visual evidence is saved under a local, unpublished visual-evidence directory:

- `desktop-light-overview.png`
- `desktop-dark-overview.png`
- `desktop-dark-file-summary.png`
- `mobile-dark-file-summary.png`
- `mobile-light-file-summary.png`
- `live-unavailable-state.png`
- `live-retry-metadata.png`
- `live-file-tree-retry.png`
- `http-unauthorized-state.png`
