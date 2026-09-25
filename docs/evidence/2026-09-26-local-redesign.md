# Local workspace visual redesign — 2026-09-26

## Interface

The local application's full visual system now uses petrol/teal and mint in dark mode, warm white and deep teal in light mode, soft gradient atmosphere, locally served Manrope typography, a compact navigation rail, a split source-import workspace, and searchable repository rows. Analysis, source, dependency, finding, documentation and AI surfaces inherit the new system. Fonts include their OFL license.

Short entry and interaction transitions replace abrupt state changes. Decorative atmosphere settles after four seconds. A persistent Reduce motion control disables animation and transforms; the system reduced-motion preference is also respected. The interface does not create nonexistent settings, timestamps, metrics or user accounts.

## Verification

- Frontend: **70 tests passed** across 17 files; TypeScript check and production build passed. The existing large diagram-bundle warning remains.
- Browser: desktop dark workspace, mobile light workspace and mobile dark report were visually inspected.
- At 390 × 844, document width was 375px with no page overflow. Repository/tab overflow stays inside navigation regions.
- Search found sampleproject, a missing-name search showed a truthful empty state, and Clear search restored the list.
- Existing saved reports loaded. A real sampleproject analysis transitioned from running to succeeded.
- Dependencies displayed 12 source nodes and 22 relationships. All analysis navigation controls were exercised, including explicit empty states on another saved repository.
- Opening src/sample/simple.py retained the public commit in the URL and highlighted source-line-1. Source content remained inert text.
- Skip to content transferred focus to main-content.
- The reduced-motion control changed computed ambient and repository-row animation names to none, and remained enabled after reload. It was then restored. The operating-system preference rule was inspected in the rendered stylesheet; OS media emulation was not used.
- AI chat answered the real add_one question with its saved-source citation in the redesigned screen. Browser error log was empty during the interaction pass.

The visual work does not extend parser language coverage or remove the existing local-model reasoning limitations. Alternate authenticated server mode retains its separate frontend flow.
