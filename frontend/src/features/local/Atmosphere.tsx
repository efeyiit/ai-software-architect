import { useEffect, useRef } from 'react';

// Coordinates follow the thread in the bundled 1536 × 1024 landscape.
const thread = 'M660 690 C775 560 905 438 1058 438 S1325 458 1250 337 S1298 291 1285 210 S1283 167 1160 156 S1280 128 1330 111';

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
      </defs>
      <image href="/brand/ariadne-landscape.png" width="1536" height="1024"/>
      <g><image className="local-fog local-fog-near" href="/brand/ariadne-mist.png" width="1536" height="1024"/><image className="local-fog local-fog-far" href="/brand/ariadne-mist.png" width="1536" height="1024"/></g>
      <path className="local-signal local-signal-glow" d={thread} pathLength="100" filter="url(#thread-glow)"/>
      <path className="local-signal" d={thread} pathLength="100"/>
    </svg>
  </div>;
}
