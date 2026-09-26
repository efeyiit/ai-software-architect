# Workspace atmosphere and controls

The mountain photograph remains stationary. Two translucent fog layers drift over its upper and middle right regions on 26- and 37-second loops. A short light travels along the landscape thread every 14 seconds. These are decorative effects, not a network activity indicator. Motion pauses when the scene leaves the viewport or the document is hidden, and is disabled by the motion control or system reduced-motion preference.

The workspace now has a sun/moon theme control, a right-hand margin caption, a transparent Ariadne mark, GitHub icons and themed cursor assets. The import area uses one source selector with GitHub and local-folder options. Hidden panels retain their input state. The light theme keeps more of the landscape visible.

Validation: 70 frontend tests passed and the production build passed, with the existing diagram bundle-size warning. Browser checks covered source selection, both themes, motion pause, a 390px viewport with no horizontal overflow, and computed custom cursor URLs. Fog transform and thread stroke position changed between observations; after pausing, fog animation was none and the signal was hidden. Low-end-device performance was not measured.

The built-in image tool produced the transparent logo and mist overlay. Prompts requested background removal while preserving the existing ribbon, and a separate translucent cyan mountain-fog texture without landscape or text. Assets are bundled under frontend/public/brand.
