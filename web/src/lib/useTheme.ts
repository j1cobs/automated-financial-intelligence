/**
 * Theme preference store (PLAN.md Phase 15, Fix 11).
 *
 * Three states, matching the token layer in `src/index.css`:
 *   'system' -- no `data-theme` stamp; `prefers-color-scheme` decides
 *   'light'  -- `data-theme="light"`, beats an OS dark preference
 *   'dark'   -- `data-theme="dark"`, beats an OS light preference
 *
 * Switching theme is a token swap, so nothing here touches component styling --
 * it only sets one attribute on `<html>`.
 *
 * Every `localStorage` access is wrapped: storage throws outright in a Safari
 * private window and when a browser is set to block site data, and a dashboard
 * must not fail to render because a preference could not be read.
 */

import { useCallback, useSyncExternalStore } from 'react';

export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'afi.theme';

function isPreference(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark';
}

function readStored(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(raw) ? raw : 'system';
  } catch {
    return 'system';
  }
}

function writeStored(preference: ThemePreference): void {
  try {
    if (preference === 'system') {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    }
  } catch {
    /* storage unavailable -- the in-memory preference still applies */
  }
}

let preference: ThemePreference = typeof window === 'undefined' ? 'system' : readStored();
const listeners = new Set<() => void>();

function emit(): void {
  for (const fn of listeners) fn();
}

/** Stamp (or clear) `data-theme` on `<html>`. */
function applyToDocument(next: ThemePreference): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (next === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', next);
  }
}

/** Read the OS preference, defensively -- jsdom has no `matchMedia`. */
export function systemTheme(): ResolvedTheme {
  try {
    return window.matchMedia?.('(prefers-color-scheme: dark)')?.matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

/** What the page actually renders as, once `'system'` is resolved. */
export function resolveTheme(next: ThemePreference): ResolvedTheme {
  return next === 'system' ? systemTheme() : next;
}

export function getThemePreference(): ThemePreference {
  return preference;
}

export function setThemePreference(next: ThemePreference): void {
  preference = next;
  writeStored(next);
  applyToDocument(next);
  emit();
}

/**
 * Apply the persisted preference to the document. Called once from module scope
 * so the attribute is set before the first paint, and exported for tests.
 */
export function initTheme(): void {
  preference = typeof window === 'undefined' ? 'system' : readStored();
  applyToDocument(preference);
}

if (typeof document !== 'undefined') {
  initTheme();
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  let media: MediaQueryList | undefined;
  try {
    // A 'system' preference must repaint when the OS flips.
    media = window.matchMedia?.('(prefers-color-scheme: dark)');
    media?.addEventListener?.('change', fn);
  } catch {
    media = undefined;
  }
  return () => {
    listeners.delete(fn);
    try {
      media?.removeEventListener?.('change', fn);
    } catch {
      /* nothing to detach */
    }
  };
}

/** Cheap, stable snapshot key: preference plus what it resolves to. */
function snapshot(): string {
  return `${preference}:${resolveTheme(preference)}`;
}

export interface ThemeControls {
  /** What the user chose, including `'system'`. */
  preference: ThemePreference;
  /** What that currently renders as. */
  theme: ResolvedTheme;
  setTheme: (next: ThemePreference) => void;
  /** Flip to the opposite of what is on screen (leaves `'system'` behind). */
  toggle: () => void;
}

export function useTheme(): ThemeControls {
  const key = useSyncExternalStore(subscribe, snapshot, () => 'system:light');
  const [storedPreference] = key.split(':') as [ThemePreference, ResolvedTheme];
  const resolved = resolveTheme(storedPreference);

  const setTheme = useCallback((next: ThemePreference) => setThemePreference(next), []);
  const toggle = useCallback(
    () => setThemePreference(resolveTheme(getThemePreference()) === 'dark' ? 'light' : 'dark'),
    [],
  );

  return { preference: storedPreference, theme: resolved, setTheme, toggle };
}
