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
 *     column currently has the smaller running height. A `ResizeObserver` on
 *     the child wrappers re-measures and re-balances if a card's content
 *     changes size later (e.g. data finishing loading, a font swap, a refetch
 *     changing row counts).
 *
 * The observer must be re-attached after every assignment. React reconciles
 * children by key *within a parent*, so a card that stays in the same column
 * keeps its wrapper `<div>`, but a card that moves to the other column gets a
 * brand-new one. An observer attached once, before the first `setColumns`,
 * keeps watching the cards that never moved and is blind to every card that
 * did -- in practice the whole right-hand column. A right-hand card growing
 * (data finishing loading, a refetch) then never re-balances, and the two
 * columns' bottoms drift apart. So the observer lives in its own effect keyed
 * on the current assignment.
 *
 * That re-attach makes idempotence mandatory. `ResizeObserver` invokes its
 * callback immediately on `observe()`, so if `rebalance` called `setColumns`
 * with a fresh array every time, each re-render would re-observe, which would
 * fire the callback, which would set state again -- forever. `rebalance` only
 * commits an assignment that differs from the current one, so the loop settles
 * as soon as the layout is stable.
 *
 * Greedy-by-running-total isn't an exact optimal bin-packing solve, but for a
 * pool of ~10 small/medium cards it lands within a card's height of balanced,
 * which is what "end at the same place" needs in practice.
 */

import {
  Children,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

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

/** True when two column assignments place the same indices in the same order. */
function sameAssignment(a: number[][], b: number[][]): boolean {
  return (
    a.length === b.length &&
    a.every((column, i) => column.length === b[i].length && column.every((v, j) => v === b[i][j]))
  );
}

interface MasonryColumnsProps {
  children: ReactNode;
  /** Applied both between the two columns and between cards within a column,
   *  and to the single stacked column below `lg`. */
  gapClassName?: string;
}

export function MasonryColumns({ children, gapClassName = 'gap-4 sm:gap-6' }: MasonryColumnsProps) {
  const items = useMemo(() => Children.toArray(children), [children]);
  const itemCount = items.length;
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [twoColumn, setTwoColumn] = useState(prefersTwoColumn);
  const [columns, setColumns] = useState<number[][]>(() => [items.map((_, i) => i), []]);
  const columnsRef = useRef(columns);

  // Declared before the measuring effect so it sees this commit's assignment.
  useLayoutEffect(() => {
    columnsRef.current = columns;
  });

  // A shrinking pool must not leave a stale node contributing its height.
  useLayoutEffect(() => {
    itemRefs.current.length = itemCount;
  }, [itemCount]);

  const rebalance = useCallback(() => {
    const isTwo = prefersTwoColumn();
    setTwoColumn(isTwo);
    let next: number[][];
    if (!isTwo) {
      next = [Array.from({ length: itemCount }, (_, i) => i), []];
    } else {
      const heights = itemRefs.current.map((el) => el?.getBoundingClientRect().height ?? 0);
      const totals = [0, 0];
      next = [[], []];
      for (let index = 0; index < itemCount; index++) {
        const target = totals[0] <= totals[1] ? 0 : 1;
        next[target].push(index);
        totals[target] += heights[index] ?? 0;
      }
    }
    // Idempotent: observe() fires immediately, so an unconditional setColumns
    // here would loop through the re-observe effect below.
    if (!sameAssignment(columnsRef.current, next)) setColumns(next);
  }, [itemCount]);

  useLayoutEffect(() => {
    // Measuring the DOM before paint is exactly what a layout effect is for.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    rebalance();
  }, [rebalance]);

  // Re-attach after every assignment: the wrappers are new nodes each time.
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => rebalance());
    itemRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [columns, twoColumn, rebalance]);

  useEffect(() => {
    try {
      const media = window.matchMedia?.(LG_BREAKPOINT_QUERY);
      media?.addEventListener?.('change', rebalance);
      return () => media?.removeEventListener?.('change', rebalance);
    } catch {
      /* matchMedia unavailable -- stays single-column, which is still correct */
    }
  }, [rebalance]);

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
