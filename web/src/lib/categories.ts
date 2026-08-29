/**
 * Display formatting for Plaid's personal-finance-category taxonomy
 * (migration 023 / `database/migrations/023_pfc_taxonomy.sql`). The API
 * returns categories raw and SCREAMING_SNAKE_CASE (`FOOD_AND_DRINK`,
 * `GENERAL_MERCHANDISE`, `UNCATEGORIZED`) -- formatting for display belongs
 * to the UI, the same rule this repo already applies to `savings_rate`
 * (stored as a fraction, formatted as a percentage only at render time).
 *
 * The raw value stays canonical everywhere else: component state, mutation
 * payloads, `<option value=...>`, filter chips. Only the rendered text runs
 * through `formatCategory`.
 */

/** `FOOD_AND_DRINK` -> `Food and Drink`, `UNCATEGORIZED` -> `Uncategorized`.
 *  Title-cases every word except `and`, which stays lowercase mid-string.
 *  Idempotent on an already-formatted or mixed-case string (splits on `_`
 *  and whitespace alike), and never throws on unexpected input -- an
 *  empty/nullish value passes through as an empty string rather than
 *  crashing a render. */
export function formatCategory(raw: string | null | undefined): string {
  if (!raw) return '';
  const words = raw.split(/[_\s]+/).filter(Boolean);
  if (words.length === 0) return raw;
  return words
    .map((word) => {
      const lower = word.toLowerCase();
      return lower === 'and' ? lower : lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(' ');
}
