/**
 * Lays an ordered pool of cards out in two columns that start and end on the
 * same line, instead of locking each card into a rigid left/right
 * `grid-cols-2` row pair. The old row-pair layout mismatched badly whenever one
 * card's content ran much longer than its row partner's (e.g. Owner Balances'
 * 11+ rows next to Income Sources' 3), leaving a large block of dead whitespace
 * under the shorter card.
 *
 * Below the `lg` breakpoint (matches the rest of the Overview tab's
 * `lg:grid-cols-2` convention) everything stacks into one column in original
 * order.
 *
 * Measuring and deciding are split. This component only measures each card and
 * applies heights; `masonryLayout.ts::planLayout` decides, as a pure function,
 * which column each card goes in and how tall it is. A greedy split of whole
 * cards can only get within one card's height of even, so the planner splits
 * first and then stretches the shorter column until both bottoms meet, with
 * cards scrolling inside their body once they pass a viewport-based ceiling.
 * Its docstring has the rules.
 *
 * A card takes part by rendering a `ScrollBody` (and, unless it's a chart, a
 * `Stack` of rows inside it). That registers, through `masonrySlot.ts`, the two
 * elements the planner needs: the scroll container (whose `clientHeight`
 * separates the card's fixed header from its body) and the Stack (whose rows
 * give the content's natural height). Rows are measured rather than the Stack
 * itself because a stretched Stack is taller than its content, while its rows
 * never are -- so the measure doesn't move when the plan does. A chart declares
 * its natural height instead of being measured, since it fills whatever height
 * it gets. A child with no `ScrollBody` is a fixed block: measured whole, never
 * sized.
 *
 * Observers must be re-attached after every plan. React reconciles children by
 * key *within a parent*, so a card that moves to the other column gets a
 * brand-new wrapper `<div>`; an observer attached once keeps watching nodes
 * that no longer exist and is blind to the cards that moved. So observers live
 * in their own effect keyed on the current plan. They watch Stack rows (and
 * fixed wrappers), never a wrapper this component sizes -- that would feed its
 * own output back in. A `MutationObserver` on each Stack catches rows added or
 * removed by a refetch, which a stretched Stack doesn't report as a resize.
 *
 * That re-attach makes idempotence mandatory. `ResizeObserver` invokes its
 * callback immediately on `observe()`, so if `rebalance` committed a fresh plan
 * every time, each re-render would re-observe, which would fire the callback,
 * which would set state again -- forever. `rebalance` only commits a plan that
 * differs from the current one (`samePlan`), so the loop settles as soon as the
 * layout is stable.
 */

import {
  Children,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  CEILING_FLOOR,
  MIN_BODY_LIST,
  ceilingFor,
  planLayout,
  samePlan,
  type CardMeasure,
  type LayoutPlan,
} from './masonryLayout';
import { MasonrySlotContext, StackRefContext, type BodyRegistration, type SlotApi } from './masonrySlot';

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

function initialPlan(count: number): LayoutPlan {
  return { columns: [Array.from({ length: count }, (_, i) => i), []], heights: Array(count).fill(null) };
}

/** Natural content height of a Stack: its rows plus the gaps between them. */
function stackContentHeight(stack: HTMLElement): number {
  const rows = Array.from(stack.children);
  const gap = parseFloat(getComputedStyle(stack).rowGap) || 0;
  const sum = rows.reduce((total, row) => total + row.getBoundingClientRect().height, 0);
  return Math.ceil(sum + gap * Math.max(0, rows.length - 1));
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
  const rootRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  const bodyRefs = useRef<(BodyRegistration | null)[]>([]);
  const [bodyVersion, setBodyVersion] = useState(0);
  const [twoColumn, setTwoColumn] = useState(prefersTwoColumn);
  const [plan, setPlan] = useState<LayoutPlan>(() => initialPlan(items.length));
  const planRef = useRef(plan);

  // Declared before the measuring effect so it sees this commit's plan.
  useLayoutEffect(() => {
    planRef.current = plan;
  });

  // A shrinking pool must not leave a stale node contributing its height.
  useLayoutEffect(() => {
    itemRefs.current.length = itemCount;
    bodyRefs.current.length = itemCount;
  }, [itemCount]);

  const slotApis = useMemo<SlotApi[]>(
    () =>
      Array.from({ length: itemCount }, (_, i) => ({
        register: (registration) => {
          bodyRefs.current[i] = registration;
          setBodyVersion((v) => v + 1);
        },
      })),
    [itemCount],
  );

  const rebalance = useCallback(() => {
    const isTwo = prefersTwoColumn();
    setTwoColumn(isTwo);
    const measures: CardMeasure[] = [];
    for (let i = 0; i < itemCount; i++) {
      const wrapperHeight = itemRefs.current[i]?.getBoundingClientRect().height ?? 0;
      const reg = bodyRefs.current[i];
      if (!reg) {
        measures.push({
          overhead: Math.ceil(wrapperHeight),
          content: 0,
          minBody: 0,
          elastic: false,
          fixed: true,
        });
        continue;
      }
      const elastic = reg.elasticHeight !== undefined;
      measures.push({
        overhead: Math.max(0, Math.ceil(wrapperHeight - reg.outer.clientHeight)),
        content: elastic ? Math.ceil(reg.elasticHeight!) : reg.stack ? stackContentHeight(reg.stack) : 0,
        minBody: reg.minBody,
        elastic,
        fixed: false,
      });
    }
    const gap = rootRef.current ? parseFloat(getComputedStyle(rootRef.current).rowGap) || 0 : 0;
    const next = planLayout(measures, {
      twoColumn: isTwo,
      ceiling: ceilingFor(window.innerHeight),
      floor: CEILING_FLOOR,
      gap,
    });
    // Idempotent: observe() fires immediately, so an unconditional setPlan
    // here would loop through the re-observe effect below.
    if (!samePlan(planRef.current, next)) setPlan(next);
  }, [itemCount]);

  useLayoutEffect(() => {
    // Measuring the DOM before paint is exactly what a layout effect is for.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    rebalance();
  }, [rebalance, bodyVersion]);

  // Re-attach after every plan: moved cards get new wrapper nodes.
  useEffect(() => {
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => rebalance());
    const mutation = typeof MutationObserver === 'undefined' ? null : new MutationObserver(() => rebalance());
    for (let i = 0; i < itemCount; i++) {
      const reg = bodyRefs.current[i];
      if (!reg) {
        const wrapper = itemRefs.current[i];
        if (wrapper) resize?.observe(wrapper);
      } else if (reg.stack) {
        Array.from(reg.stack.children).forEach((row) => resize?.observe(row));
        mutation?.observe(reg.stack, { childList: true });
      }
      // Elastic bodies declare their height; nothing to observe.
    }
    return () => {
      resize?.disconnect();
      mutation?.disconnect();
    };
  }, [plan, twoColumn, rebalance, bodyVersion, itemCount]);

  useEffect(() => {
    // The ceiling follows the viewport height.
    window.addEventListener('resize', rebalance);
    return () => window.removeEventListener('resize', rebalance);
  }, [rebalance]);

  useEffect(() => {
    try {
      const media = window.matchMedia?.(LG_BREAKPOINT_QUERY);
      media?.addEventListener?.('change', rebalance);
      return () => media?.removeEventListener?.('change', rebalance);
    } catch {
      /* matchMedia unavailable -- stays single-column, which is still correct */
    }
  }, [rebalance]);

  const renderItem = (index: number) => {
    const height = plan.heights[index];
    return (
      <MasonrySlotContext.Provider key={index} value={slotApis[index] ?? null}>
        <div
          ref={(el) => {
            itemRefs.current[index] = el;
          }}
          style={height != null ? { height } : undefined}
        >
          {items[index]}
        </div>
      </MasonrySlotContext.Provider>
    );
  };

  if (!twoColumn) {
    return (
      <div ref={rootRef} className={`flex flex-col ${gapClassName}`}>
        {items.map((_, index) => renderItem(index))}
      </div>
    );
  }

  return (
    <div ref={rootRef} className={`flex flex-col lg:flex-row ${gapClassName}`}>
      {plan.columns.map((column, colIndex) => (
        <div key={colIndex} className={`flex min-w-0 flex-1 flex-col ${gapClassName}`}>
          {column.map((itemIndex) => renderItem(itemIndex))}
        </div>
      ))}
    </div>
  );
}

interface ScrollBodyProps {
  children: ReactNode;
  /** Smallest body height before the card may scroll. */
  minBody?: number;
  /** A chart's natural height. Marks the body elastic: it fills any extra
   *  height it's given, and scrolls rather than compress below this. */
  elasticHeight?: number;
}

/** A card's body inside a masonry slot: scrolls when allotted less than its
 *  content, so the card's title and caption stay put. Outside a slot it renders
 *  its children unchanged. */
export function ScrollBody({ children, minBody = MIN_BODY_LIST, elasticHeight }: ScrollBodyProps) {
  const slot = useContext(MasonrySlotContext);
  const outer = useRef<HTMLDivElement | null>(null);
  const [stack, setStack] = useState<HTMLElement | null>(null);

  useLayoutEffect(() => {
    if (!slot || !outer.current) return;
    slot.register({
      outer: outer.current,
      stack: elasticHeight === undefined ? stack : null,
      minBody,
      elasticHeight,
    });
    return () => slot.register(null);
  }, [slot, stack, minBody, elasticHeight]);

  if (!slot) return <>{children}</>;
  return (
    <div ref={outer} className="min-h-0 flex-1 overflow-y-auto">
      {elasticHeight !== undefined ? (
        <div style={{ height: '100%', minHeight: elasticHeight }}>{children}</div>
      ) : (
        <div className="flex min-h-full flex-col">
          <StackRefContext.Provider value={setStack}>{children}</StackRefContext.Provider>
        </div>
      )}
    </div>
  );
}

interface StackProps {
  as?: 'div' | 'ul';
  /** The gap between rows, e.g. `gap-1.5`. Extra height is added on top of it. */
  className?: string;
  /** The rows. Every element of a card's body must be one of them: anything
   *  outside the Stack isn't measured. */
  children: ReactNode;
}

/** The rows of a non-chart card body. In a stretched card, extra height becomes
 *  equal slots above, between and below the rows (a single row is centered);
 *  otherwise it's a plain column with the given gap. */
export function Stack({ as: Tag = 'div', className = 'gap-1.5', children }: StackProps) {
  const setStack = useContext(StackRefContext);
  if (!setStack) return <Tag className={`flex flex-col ${className}`}>{children}</Tag>;
  return (
    <Tag ref={setStack} className={`flex flex-1 flex-col justify-evenly ${className}`}>
      {children}
    </Tag>
  );
}
