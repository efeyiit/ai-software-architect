# Sidebar spacing on wide monitors

The previous width cap still centered the home content within the remaining screen, leaving a large gap beside the sidebar. The home column now starts beside the sidebar rather than using automatic horizontal margins. Header and footer content use the same left inset while retaining the 1200px column cap.

Validation: production build passed. At a 2560x1440 browser viewport, the sidebar ends at x=224 and the hero and breadcrumb begin at x=272: a 48px gap. The main column measures 1200px and the document has no horizontal overflow. Browser screenshot inspection confirmed the left alignment. Mobile rules are unchanged.
