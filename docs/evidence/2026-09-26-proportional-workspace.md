# Proportional home workspace

The side-by-side layout left too much unused vertical space. The home returns to the original sequence: introduction, import controls, saved repositories. On large desktop viewports the whole home shell now scales together, including text, controls, spacing, and scenery. Scale is 1.25 from 1800px, 1.5 from 2200px, and 1.6 from 2500px. Sidebar viewport height is compensated for that scale. Smaller screens and repository report views retain their existing scale.

Production build passed. Browser checks at 2560x1440 reported scale 1.6, a 1440px sidebar height, no horizontal overflow, and the repository list extending below the fold rather than leaving the lower screen empty. At 1920x1080 the scale was 1.25 with no horizontal overflow. This supersedes the previous two-column home layout.
