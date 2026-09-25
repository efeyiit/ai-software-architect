# Frontend application shell

T26 supplies the Ariadne entry experience and a minimal route shell for `/login`, `/dashboard`, and `/repository/:id`. The shell uses native links so routes work without an additional router dependency, includes a keyboard skip link and responsive mobile navigation, and labels unavailable GitHub/authentication/analysis capabilities without simulating success or repository data.

## Visual style and interaction feedback

The shell uses the requested `#F3F4F4` background, `#2C2C2C` text, `#853953` primary action, and `#612D53` dark accent. The stylesheet requests `LL Circular` with `Circular Std` and Arial system fallbacks. No LL Circular font file was present in the project assets, so the actual licensed font is not bundled or rendered here. Disabled GitHub actions name their visible reason through `aria-describedby`; route navigation has active, hover, pressed, and keyboard-focus states. There are no input forms or connected operations in T26, so validation, progress, success, and error states are not fabricated.

## Start and verify

From `frontend/`, run `pnpm dev` to start the Vite app, `pnpm test` to run the frontend tests, and `pnpm build` to type-check and bundle the app.

## Route boundaries

- `/` and `/login`: sign-in screen; GitHub sign-in is visibly unavailable and disabled.
- `/dashboard`: empty workspace and repository list; connection action is visibly unavailable and disabled.
- `/repository/:id` (and nested repository paths): repository context with an explicit not-connected state.
- Other paths: not-found state.

Authentication, repository connection, analysis data, and repository reports are not implemented by this shell.
