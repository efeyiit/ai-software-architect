# Fog clipping correction

The previous CSS overlay removal did not fix the visible rectangle. The SVG fog mask blurred a 340-unit stroke with a filter using default object bounding-box bounds. Those bounds clipped the stroke and its blur into sharp horizontal and vertical edges.

The fog filter and mask now use explicit scene coordinates with a 300-unit margin. The moving fog, stationary blurred landscape, and existing reduced-motion handling remain intact.

Validation: TypeScript and production build passed. Browser inspection of the dark desktop scene confirmed the reported upper and right clipping edges are absent after reload.
