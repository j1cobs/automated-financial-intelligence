/// <reference types="node" />
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * Guards the bug behind the dashboard's original dark-mode failure: every
 * component was tokenized except the app shell (Dashboard.tsx, SignIn.tsx,
 * LoadingScreen.tsx), because no agent owned those files. Dark mode only
 * works if colors go through index.css's `--surface-*`/`--text-*`/`--border-*`
 * tokens (consumed as `bg-surface-*`, `text-ink*`, `border-hairline`/`-strong`,
 * `bg-ink`/`text-on-emphasis`) instead of Tailwind's raw slate/gray palette,
 * which is frozen to its light-mode values and never flips.
 */

const SRC_DIR = join(__dirname, '..');

// Raw Tailwind grayscale utilities that bypass the token layer. `black`/`white`
// are intentionally excluded: `bg-black/40` is a theme-independent modal
// scrim (FilterBar.tsx), not a themed surface/text/border color.
const RAW_COLOR_PATTERN =
  /\b(?:bg|text|border|ring|divide|placeholder|from|via|to)-(?:slate|gray|zinc|neutral|stone)-\d{2,3}\b/;

function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      files.push(...collectSourceFiles(full));
      continue;
    }
    if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      files.push(full);
    }
  }
  return files;
}

describe('no raw Tailwind grayscale colors outside the token layer', () => {
  it('finds none in web/src', () => {
    const offenders: string[] = [];
    for (const file of collectSourceFiles(SRC_DIR)) {
      const content = readFileSync(file, 'utf-8');
      const match = content.match(RAW_COLOR_PATTERN);
      if (match) {
        offenders.push(`${relative(SRC_DIR, file)}: ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
