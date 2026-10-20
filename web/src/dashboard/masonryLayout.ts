/**
 * Pure planner for `MasonryColumns`: given each card's measured size, decides
 * which column it goes in and how tall it should be, so both columns start and
 * end on the same line. No DOM and no React, so every rule is unit-testable
 * with plain numbers; the component only measures and applies the result.
 *
 * A greedy split of whole cards can only get within one card's height of even,
 * so the planner splits first, then stretches the shorter column. The rules,
 * in order (all integer px):
 *  1. Wanted height = min(natural, max(ceiling, overhead + minBody)). A card
 *     scrolls only when its content passes the ceiling, and the max() keeps a
 *     scrolling chart from being squeezed below its minimum visible body.
 *     Fixed cards (no scroll body to size) keep their natural height.
 *  2. Greedy split on wanted heights, in order, to whichever column is shorter;
 *     `<=` sends a tie left. Same rule as before, so the layout stays familiar.
 *  3. For the shorter column, fill the gap D to the taller one:
 *     a. grow its clipped cards back toward their full content;
 *     b. grow its elastic cards (charts) up to 125% of their chart height;
 *     c. shrink the taller column's clipped cards (they scroll a bit more), no
 *        lower than max(floor, overhead + minBody), so the target falls instead;
 *     d. spread whatever remains evenly across the shorter column's cards.
 *     Growth comes before shrinking so cards show as much content as possible;
 *     the spread is last because it only adds white space.
 * The result is deterministic, and the bottoms are exactly equal whenever the
 * shorter column holds at least one sizeable card.
 */

export const CEILING_RATIO = 0.7;
export const CEILING_FLOOR = 560;
export const MIN_BODY_LIST = 120;
export const MIN_BODY_CHART = 250;
export const ELASTIC_MAX_GROWTH = 0.25;

export interface CardMeasure {
  /** Card height minus its scroll body: title, caption, headerExtra, padding, border. Integer px (ceil). */
  overhead: number;
  /** Natural body content height. Integer px (ceil). For elastic cards, the declared chart height. */
  content: number;
  /** Smallest body height before the card may scroll. */
  minBody: number;
  /** Body can usefully fill extra height (charts). */
  elastic: boolean;
  /** No ScrollBody registered: measured as a whole, never clipped, grown, shrunk or given a height. */
  fixed: boolean;
}

export interface LayoutPlan {
  /** Indices per column; stacked mode = one column in original order, plus an empty second column. */
  columns: number[][];
  /** Allotted card height per index; null = leave unsized (fixed card). */
  heights: (number | null)[];
}

/** Tallest a card may be before its body scrolls: 70% of the viewport, never under the floor. */
export function ceilingFor(viewportHeight: number): number {
  return Math.max(Math.round(CEILING_RATIO * viewportHeight), CEILING_FLOOR);
}

/**
 * Water-fill: hands out `amount` px in equal shares, never past a card's room
 * (Infinity = unlimited). Spare pixels from an uneven share go 1 px each to the
 * first cards, so the same input always yields the same split.
 */
function distribute(amount: number, rooms: number[]): { given: number[]; left: number } {
  const given = rooms.map(() => 0);
  let left = amount;
  for (;;) {
    const open = rooms.flatMap((room, i) => (given[i] < room ? [i] : []));
    if (open.length === 0 || left <= 0) break;
    const share = Math.floor(left / open.length);
    if (share === 0) {
      // Fewer pixels than cards: one each, in order.
      for (const i of open) {
        if (left === 0) break;
        given[i] += 1;
        left -= 1;
      }
      break;
    }
    for (const i of open) {
      const g = Math.min(share, rooms[i] - given[i]);
      given[i] += g;
      left -= g;
    }
  }
  return { given, left };
}

export function planLayout(
  cards: CardMeasure[],
  opts: { twoColumn: boolean; ceiling: number; floor: number; gap: number },
): LayoutPlan {
  const { twoColumn, ceiling, floor, gap } = opts;
  const natural = cards.map((c) => c.overhead + c.content);
  const wanted = cards.map((c, i) =>
    c.fixed ? natural[i] : Math.min(natural[i], Math.max(ceiling, c.overhead + c.minBody)),
  );
  const toHeights = (h: number[]): (number | null)[] => h.map((v, i) => (cards[i].fixed ? null : v));

  if (!twoColumn) {
    return { columns: [cards.map((_, i) => i), []], heights: toHeights(wanted) };
  }

  const columns: number[][] = [[], []];
  const totals = [0, 0];
  cards.forEach((_, i) => {
    const target = totals[0] <= totals[1] ? 0 : 1;
    columns[target].push(i);
    totals[target] += wanted[i];
  });

  const height = [...wanted];
  const bottom = (column: number[]) =>
    column.reduce((sum, i) => sum + height[i], 0) + gap * Math.max(0, column.length - 1);
  const [t0, t1] = [bottom(columns[0]), bottom(columns[1])];
  if (t0 === t1) return { columns, heights: toHeights(height) };

  const shorter = columns[t0 < t1 ? 0 : 1];
  const taller = columns[t0 < t1 ? 1 : 0];
  // Whole pixels only: a fractional gap (e.g. 1.5rem at a 15px root font) would
  // otherwise leave a sub-pixel remainder that `distribute` can't place exactly.
  let deficit = Math.round(Math.abs(t0 - t1));

  // a. Clipped cards in the shorter column grow back toward their full content.
  for (const i of shorter) {
    if (deficit === 0) break;
    if (cards[i].fixed || natural[i] <= height[i]) continue;
    const grow = Math.min(deficit, natural[i] - height[i]);
    height[i] += grow;
    deficit -= grow;
  }

  // b. Elastic cards (charts) grow, up to 125% of their chart height.
  const elastic = shorter.filter((i) => !cards[i].fixed && cards[i].elastic);
  const grown = distribute(
    deficit,
    elastic.map((i) =>
      Math.max(0, cards[i].overhead + Math.ceil(cards[i].content * (1 + ELASTIC_MAX_GROWTH)) - height[i]),
    ),
  );
  elastic.forEach((i, k) => (height[i] += grown.given[k]));
  deficit = grown.left;

  // c. The taller column's clipped cards scroll a bit more, never past the floor.
  const clipped = taller.filter((i) => !cards[i].fixed && natural[i] > height[i]);
  const shrunk = distribute(
    deficit,
    clipped.map((i) => Math.max(0, height[i] - Math.max(floor, cards[i].overhead + cards[i].minBody))),
  );
  clipped.forEach((i, k) => (height[i] -= shrunk.given[k]));
  deficit = shrunk.left;

  // d. Whatever is left becomes equal white space across the shorter column.
  const sizeable = shorter.filter((i) => !cards[i].fixed);
  if (deficit > 0 && sizeable.length > 0) {
    const spread = distribute(
      deficit,
      sizeable.map(() => Infinity),
    );
    sizeable.forEach((i, k) => (height[i] += spread.given[k]));
  }

  return { columns, heights: toHeights(height) };
}

/** True when two plans put the same cards in the same columns at the same heights. */
export function samePlan(a: LayoutPlan, b: LayoutPlan): boolean {
  return (
    a.columns.length === b.columns.length &&
    a.columns.every(
      (column, i) => column.length === b.columns[i].length && column.every((v, j) => v === b.columns[i][j]),
    ) &&
    a.heights.length === b.heights.length &&
    a.heights.every((h, i) => h === b.heights[i])
  );
}
