# Wide-screen workspace spacing

At desktop sizes, the home content is capped at 1200px including 48px side padding. Header and footer content align with that column. The hero font is capped at 54px and source choices stay 40px from the section heading instead of moving to the far edge. The landscape remains full width. Repository analysis views retain their existing width.

Validation: production build passed. At a 2560x1440 browser viewport, measured main width was 1200px, hero font 54px, source gap 40px, and no horizontal document overflow. At 390x844 the source controls stack and no horizontal document overflow was found. Large-viewport screenshot capture showed stitching artifacts, so it is not treated as reliable visual evidence of the full composition; DOM measurements and normal/mobile browser inspection are the available evidence.
