import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  THEME_STORAGE_KEY,
  getThemePreference,
  initTheme,
  resolveTheme,
  setThemePreference,
} from './useTheme';

describe('theme preference store', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    initTheme();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults to system, leaving data-theme unstamped', () => {
    expect(getThemePreference()).toBe('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('stamps and persists an explicit choice', () => {
    setThemePreference('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    setThemePreference('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
  });

  it('restores the persisted choice on a fresh load', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    initTheme();
    expect(getThemePreference()).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('clears the stamp and the stored value when returning to system', () => {
    setThemePreference('dark');
    setThemePreference('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('ignores a corrupt stored value instead of stamping it', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'chartreuse');
    initTheme();
    expect(getThemePreference()).toBe('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('survives storage that throws (private mode, blocked site data)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });

    expect(() => initTheme()).not.toThrow();
    expect(getThemePreference()).toBe('system');

    // The choice still applies in memory and on the document.
    expect(() => setThemePreference('dark')).not.toThrow();
    expect(getThemePreference()).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('resolves an explicit preference without consulting the OS', () => {
    expect(resolveTheme('dark')).toBe('dark');
    expect(resolveTheme('light')).toBe('light');
  });
});
