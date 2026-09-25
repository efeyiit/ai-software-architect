import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';
const themeKey = 'ariadne:theme';

function initialTheme(): Theme {
  if (typeof document === 'undefined') return 'light';
  const applied = document.documentElement.dataset.theme;
  if (applied === 'light' || applied === 'dark') return applied;
  try {
    const saved = window.localStorage.getItem(themeKey);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // The system preference remains usable when storage is unavailable.
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [feedback, setFeedback] = useState<{ id: number; message: string } | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (!feedback) return;
    const timeout = window.setTimeout(() => setFeedback(null), 2400);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  function toggle() {
    const next = theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    setTheme(next);
    setFeedback((current) => ({ id: (current?.id ?? 0) + 1, message: next === 'dark' ? 'Dark mode is on' : 'Light mode is on' }));
    try {
      window.localStorage.setItem(themeKey, next);
    } catch {
      // The current page still changes theme without persistent storage.
    }
  }

  return <>
    <button className="theme-toggle" type="button" aria-label="Dark mode" aria-pressed={theme === 'dark'} onClick={toggle}>
      <span className="theme-toggle__icon" aria-hidden="true">{theme === 'dark' ? '☾' : '☼'}</span>
      <span className="theme-toggle__track" aria-hidden="true"><span className="theme-toggle__thumb"/></span>
      <span>Dark mode</span>
    </button>
    {feedback && <span className="theme-feedback" role="status" key={feedback.id}><span className="theme-feedback__dot" aria-hidden="true"/>{feedback.message}</span>}
  </>;
}
