# Workspace visual correction — 2026-09-26

The home background now uses a bundled atmospheric landscape instead of only CSS gradients. The import area is an open, asymmetric layout with an inline GitHub URL action and a smaller folder picker. Supporting copy describes actions directly. Self-hosted fonts moved under the static brand route to load correctly in local mode.

Buttons and links use a pointer, text fields use a text cursor, unavailable controls use not-allowed, and pending import, analysis and chat controls explicitly expose aria-busy with a wait cursor.

Validation: 70 frontend tests passed; production build passed (existing diagram chunk-size warning). Browser inspection covered desktop dark, 390px dark/light, loaded Manrope, actual landscape display, pointer/text/file-picker computed cursors, and no document overflow at 375px content width. Existing sampleproject analysis completed successfully; it completed too quickly to capture its transient wait cursor, which was checked in component and CSS definitions.

The background was generated with the built-in image tool from the approved concept, requesting only a dark petrol mineral landscape, cyan mist and a fine mint thread, with quiet space on the left and no text or UI. Asset: frontend/public/brand/ariadne-landscape.png.
