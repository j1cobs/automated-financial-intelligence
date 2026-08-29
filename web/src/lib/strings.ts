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
    /** Accessible name for a tile made clickable via `onDrillDown`. */
    drillDownLabel: (metricLabel: string) => `View details for ${metricLabel}`,
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
  loading: {
    /** Accessible name for a `<TabSkeleton>` region (PLAN.md Phase 15, Fix 14) --
     *  the skeleton itself carries no readable text, so screen readers need this. */
    tabLabel: 'Loading…',
    /** Button label on `<ErrorState>`, wired to the failed query's `refetch`. */
    retryLabel: 'Retry',
    /** Inline banner shown next to a ledger row whose edit failed and was rolled
     *  back -- see `mutations.ts`'s `onError`. */
    editFailed: 'Failed to save your change. It has been reverted — please try again.',
  },
  ledger: {
    /** Confirmation shown after a category correction backfills other rows from
     *  the same merchant (PLAN.md Phase 18, Step 4's merchant-memory cascade).
     *  Only rendered when `backfilled_count > 0` -- most corrections have
     *  nothing to backfill and this stays silent. */
    categoryBackfilled: (count: number): string =>
      `Updated ${count} other ${count === 1 ? 'transaction' : 'transactions'} from this merchant.`,
  },
} as const;
