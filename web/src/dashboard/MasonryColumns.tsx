/**
 * Balances an ordered pool of cards into two columns that end at (or very
 * near) the same total height, instead of locking each card into a rigid
 * left/right `grid-cols-2` row pair. The old row-pair layout mismatched badly
 * whenever one card's content ran much longer than its row partner's (e.g.
 * Owner Balances' 11+ rows next to Income Sources' 3), leaving a large block
 * of dead whitespace under the shorter card.
 *
 * Below the `lg` breakpoint (matches the rest of the Overview tab's
 * `lg:grid-cols-2` convention) everything stacks into one column in original
 * order -- no balancing needed on a narrow viewport.
 *
 * Balancing works in two passes:
 *  1. Children first render in original order (a guessed single-column
 *     layout) so each one lays out normally in the DOM and gets a real
 *     measured height. The cards in this pool size themselves from row/entry
 *     count or a fixed pixel height, not from their container's width, so
 *     measuring before the final column split is a safe stand-in for their
 *     eventual half-width height.
 *  2. A `useLayoutEffect` measures every child (before paint, so there's no
 *     visible flash) and greedily assigns each card, in order, to whichever
 *     column currently has the smaller running height. A `ResizeObserver` per
 *     child re-measures and re-balances if a card's content changes size
 *     later (e.g. a data refetch changing row counts).
 *
 * Greedy-by-running-total isn't an exact optimal bin-packing solve, but for a
 * pool of ~10 small/medium cards it lands within a card's height of balanced,
 * which is what "end at the same place" needs in practice.
 */

import { Children, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';

const LG_BREAKPOINT_QUERY = '(min-width: 1024px)';

/** Defensive, mirroring `lib/useTheme.ts::systemTheme` -- jsdom (tests) has no
 *  `matchMedia`, and a dashboard must not fail to render over a missing API. */
function prefersTwoColumn(): boolean {
  try {
    return window.matchMedia?.(LG_BREAKPOINT_QUERY)?.matches ?? true;
  } catch {
    return true;
  }
}

interface MasonryColumnsProps {
  children: ReactNode;
  /** Applied both between the two columns and between cards within a column,
   *  and to the single stacked column below `lg`. */
  gapClassName?: string;
}

export function MasonryColumns({ children, gapClassName = 'gap-4 sm:gap-6' }: MasonryColumnsProps) {
  const items = useMemo(() => Children.toArray(children), [children]);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [twoColumn, setTwoColumn] = useState(prefersTwoColumn);
  const [columns, setColumns] = useState<number[][]>(() => [items.map((_, i) => i), []]);

  useLayoutEffect(() => {
    function rebalance() {
      const isTwo = prefersTwoColumn();
      setTwoColumn(isTwo);
      if (!isTwo) {
        setColumns([items.map((_, i) => i), []]);
        return;
      }
      const heights = itemRefs.current.map((el) => el?.getBoundingClientRect().height ?? 0);
      const totals = [0, 0];
      const next: number[][] = [[], []];
      items.forEach((_, index) => {
        const target = totals[0] <= totals[1] ? 0 : 1;
        next[target].push(index);
        totals[target] += heights[index];
      });
      setColumns(next);
    }

    rebalance();

    const cleanups: Array<() => void> = [];
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(() => rebalance());
      itemRefs.current.forEach((el) => el && observer.observe(el));
      cleanups.push(() => observer.disconnect());
    }
    try {
      const media = window.matchMedia?.(LG_BREAKPOINT_QUERY);
      media?.addEventListener?.('change', rebalance);
      cleanups.push(() => media?.removeEventListener?.('change', rebalance));
    } catch {
      /* matchMedia unavailable -- stays single-column, which is still correct */
    }

    return () => cleanups.forEach((fn) => fn());
    // Item CONTENT changes are covered by the ResizeObserver above; this only
    // needs to re-run the initial measurement pass when the pool itself changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length]);

  if (!twoColumn) {
    return (
      <div className={`flex flex-col ${gapClassName}`}>
        {items.map((item, index) => (
          <div
            key={index}
            ref={(el) => {
              itemRefs.current[index] = el;
            }}
          >
            {item}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={`flex flex-col lg:flex-row ${gapClassName}`}>
      {columns.map((column, colIndex) => (
        <div key={colIndex} className={`flex min-w-0 flex-1 flex-col ${gapClassName}`}>
          {column.map((itemIndex) => (
            <div
              key={itemIndex}
              ref={(el) => {
                itemRefs.current[itemIndex] = el;
              }}
            >
              {items[itemIndex]}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
