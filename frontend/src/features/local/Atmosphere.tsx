import { useEffect, useRef } from 'react';

// The filament and its light share one path through the new valley plate.
const thread = 'M1080 824 C1000 780 867 761 930 715 S1150 659 1240 573 S1260 496 1172 450 S1256 361 1330 314 S1340 265 1270 238 S1317 184 1390 149';

export function Atmosphere() {
  const scene = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = scene.current;
    if (!element) return;
    let inView = true;
    const update = () => { element.dataset.paused = String(document.hidden || !inView); };
    update();
    document.addEventListener('visibilitychange', update);
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      update();
    });
    observer.observe(element);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', update); };
  }, []);
  return <div className="local-landscape" aria-hidden="true" ref={scene}>
    <svg viewBox="0 0 1536 1024" preserveAspectRatio="xMaxYMin slice" className="local-landscape-art">
      <defs>
        <filter id="thread-glow"><feGaussianBlur stdDeviation="4"/></filter>
        {/* Include the wide stroke and blur halo; the default path bounds clip them into a rectangle. */}
        <filter id="valley-feather" filterUnits="userSpaceOnUse" x="-300" y="-300" width="2136" height="1624"><feGaussianBlur stdDeviation="45"/></filter>
        <mask id="valley-mist" maskUnits="userSpaceOnUse" x="-300" y="-300" width="2136" height="1624"><path d={thread} fill="none" stroke="white" strokeWidth="340" filter="url(#valley-feather)"/></mask>
        <linearGradient id="fog-edge-x"><stop stopColor="white" stopOpacity="0"/><stop offset=".16" stopColor="white"/><stop offset=".8" stopColor="white"/><stop offset="1" stopColor="white" stopOpacity="0"/></linearGradient>
        <linearGradient id="fog-edge-y" x2="0" y2="1"><stop stopColor="white" stopOpacity="0"/><stop offset=".18" stopColor="white"/><stop offset=".8" stopColor="white"/><stop offset="1" stopColor="white" stopOpacity="0"/></linearGradient>
        <mask id="fog-texture-x" maskUnits="userSpaceOnUse" x="0" y="0" width="1536" height="1024"><rect width="1536" height="1024" fill="url(#fog-edge-x)"/></mask>
        <mask id="fog-texture-y" maskUnits="userSpaceOnUse" x="0" y="0" width="1536" height="1024"><rect width="1536" height="1024" fill="url(#fog-edge-y)"/></mask>
      </defs>
      <image href="/brand/ariadne-valley.png" width="1536" height="1024"/>
      <path className="local-filament" d={thread}/>
      <path className="local-signal local-signal-glow" d={thread} pathLength="100" filter="url(#thread-glow)"/>
      <path className="local-signal" d={thread} pathLength="100"/>
      {/* Feather the texture itself before moving it, so its canvas edges can never drift into view. */}
      <g mask="url(#valley-mist)">{['near', 'far'].map(layer => <g key={layer} className={`local-fog local-fog-${layer}`}><g mask="url(#fog-texture-y)"><image mask="url(#fog-texture-x)" href="/brand/ariadne-mist.png" width="1536" height="1024"/></g></g>)}</g>
    </svg>
  </div>;
}
