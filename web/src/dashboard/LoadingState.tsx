/**
 * Shared loading/error chrome for the four dashboard tabs (PLAN.md Phase 15, Fix 14).
 *
 * Every tab used to render a bare "Loading X data..." string while its query resolved,
 * and a dead-end error card with no way to recover. `<TabSkeleton>` replaces the former
 * with layout-shaped placeholder blocks -- a KPI row plus a couple of chart-sized blocks --
 * so a tab switch shows the shape of what's coming instead of flashing empty space or a
 * line of text. `<ErrorState>` replaces the latter with a message plus a `Retry` button
 * wired to the failed query's own `refetch`.
 *
 * Tokenized throughout (no hex, no raw Tailwind colour names) and themed automatically
 * through the `bg-surface-*`/`text-*`/`border-*` utilities `index.css`'s `@theme inline`
 * block defines.
 */

import { strings } from '../lib/strings';

/** One placeholder block. `animate-pulse` is Tailwind's built-in opacity pulse -- no
 *  custom keyframes needed for "subtle". */
function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-surface-2 ${className}`} />;
}

/**
 * Layout-shaped placeholder for a tab still loading its primary query: a title bar, a
 * row of KPI tiles, and two chart-sized blocks -- roughly what every tab renders once
 * data arrives, so the page doesn't visibly jump when it does.
 */
export function TabSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label={strings.loading.tabLabel}>
      <SkeletonBlock className="h-6 w-40" />

      <div className="grid grid-cols-2 gap-2 sm:gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <SkeletonBlock key={i} className="h-16 sm:h-20" />
        ))}
      </div>

      <SkeletonBlock className="h-56 w-full sm:h-80" />
      <SkeletonBlock className="h-56 w-full sm:h-80" />

      {/* The blocks above are decorative (aria-hidden by default, no text content) --
          this is the only thing assistive tech announces. */}
      <span className="sr-only">{strings.loading.tabLabel}</span>
    </div>
  );
}

/**
 * Error card with a recovery action. `onRetry` is normally a query's `refetch` --
 * omit it for a failure that genuinely has no retry (there is none of those yet
 * among this phase's callers, but the prop stays optional rather than assumed).
 */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface-2 p-4 sm:p-6" role="alert">
      <p className="text-sm text-neg-text">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 min-h-9 rounded-md border border-strong bg-surface-1 px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface-3"
        >
          {strings.loading.retryLabel}
        </button>
      )}
    </div>
  );
}
