# Moving fog texture edges

The expanded SVG filter fixed the stationary clipping rectangle, but the translated PNG still had visible canvas edges. Each fog texture now fades to zero opacity on all four sides, inside the animated group. Both perpendicular masks travel with the texture, so the fade remains attached throughout translation and scaling. The separate valley mask still controls the fog's overall placement.

The stationary landscape blur was initially increased from 3 to 8 units. User feedback found that too strong; it is now 4 units, preserving landscape detail while softening it. The moving texture edge masks are unchanged, and no rectangular color overlay is added.

Validation: TypeScript and production build passed. Browser inspection checked the moving dark scene at separate animation positions and light theme. Existing large diagram bundle warning remains.
