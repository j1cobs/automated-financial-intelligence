/**
 * Single source of user-facing copy for the components under PLAN.md Phase 15,
 * Fixes 12-14 (`MetricTile`, the metric tooltip popover, cross-filter hints).
 *
 * English-only for now. The point of routing every string through here is
 * that adding a second locale later is a translation pass over this one
 * module, not a hunt through JSX for hardcoded text -- mirrors the intent of
 * Streamlit's `_STRINGS` en/fr toggle (`app/dashboard.py:1335`) without
 * committing to its shape.
 *
 * Deliberately NOT a framework: a flat object of constants and small pure
 * formatter functions. No lookup-by-key indirection, no ICU message syntax --
 * just JS functions a translator (or another engineer) can read top to bottom.
 */

export const strings = {
  metricTile: {
    /** Accessible name for the info-popover trigger button. */
    infoButtonLabel: (metricLabel: string) => `More about ${metricLabel}`,
    formulaLabel: 'Formula',
    windowLabel: 'Window',
    excludesLabel: 'Excludes',
    /**
     * "12% above your 3-month average" / "8% below your 6-month average" /
     * "at your 3-month average" when the delta rounds to zero. `"N-month"` is
     * a compound modifier (like "a 6-month lease") and stays singular
     * regardless of N -- "3-months average" is not idiomatic English.
     * Direction words describe where the value sits relative to its
     * baseline, not whether that is good or bad -- the badge next to this
     * text carries the polarity-aware colour, glyph, and word (see
     * `lib/polarity.ts`).
     */
    baselineComparison(deltaPct: number, baselineMonths: number): string {
      const pct = Math.round(Math.abs(deltaPct) * 100);
      if (pct === 0) {
        return `at your ${baselineMonths}-month average`;
      }
      const direction = deltaPct > 0 ? 'above' : 'below';
      return `${pct}% ${direction} your ${baselineMonths}-month average`;
    },
  },
  crossFilter: {
    /** Discoverability caption placed under a clickable category chart. */
    categoryHint: 'Click a bar to add that category to your filters.',
  },
} as const;
