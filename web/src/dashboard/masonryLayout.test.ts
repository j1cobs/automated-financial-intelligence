import { describe, it, expect } from 'vitest';
import {
  CEILING_FLOOR,
  ELASTIC_MAX_GROWTH,
  MIN_BODY_CHART,
  MIN_BODY_LIST,
  ceilingFor,
  planLayout,
  samePlan,
  type CardMeasure,
  type LayoutPlan,
} from './masonryLayout';

/** A list-style card unless overridden. */
function card(overhead: number, content: number, extra: Partial<CardMeasure> = {}): CardMeasure {
  return { overhead, content, minBody: MIN_BODY_LIST, elastic: false, fixed: false, ...extra };
}

/** Column bottom as the browser would lay it out: heights plus the gaps between cards. */
function bottoms(plan: LayoutPlan, cards: CardMeasure[], gap: number): number[] {
  return plan.columns.map(
    (column) =>
      column.reduce((sum, i) => sum + (plan.heights[i] ?? cards[i].overhead + cards[i].content), 0) +
      gap * Math.max(0, column.length - 1),
  );
}

/** Small seeded PRNG so the property test is reproducible. */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const OPTS = { twoColumn: true, ceiling: 500, floor: 400, gap: 10 };

describe('constants', () => {
  it('match the documented values', () => {
    expect(CEILING_FLOOR).toBe(560);
    expect(MIN_BODY_LIST).toBe(120);
    expect(MIN_BODY_CHART).toBe(250);
    expect(ELASTIC_MAX_GROWTH).toBe(0.25);
  });
});

describe('ceilingFor', () => {
  it('is 70% of the viewport, never below the floor', () => {
    expect(ceilingFor(824)).toBe(577);
    expect(ceilingFor(714)).toBe(560);
    expect(ceilingFor(1080)).toBe(756);
  });
});

describe('wanted height', () => {
  it('stacked: keeps order, clips to the ceiling, never stretches', () => {
    const cards = [card(60, 200), card(60, 900), card(60, 50)];
    const plan = planLayout(cards, { ...OPTS, twoColumn: false });
    expect(plan.columns).toEqual([[0, 1, 2], []]);
    expect(plan.heights).toEqual([260, 500, 110]);
  });

  it('a card over the ceiling is clipped; one under it keeps its natural height', () => {
    const plan = planLayout([card(60, 900), card(60, 200)], { ...OPTS, twoColumn: false });
    expect(plan.heights).toEqual([500, 260]);
  });

  it('a chart whose overhead + minBody is above the ceiling gets overhead + minBody', () => {
    const chart = card(100, 400, { elastic: true, minBody: MIN_BODY_CHART });
    const plan = planLayout([chart], { ...OPTS, twoColumn: false, ceiling: 300 });
    expect(plan.heights).toEqual([350]);
  });

  it('stacked: fixed cards are left unsized', () => {
    const plan = planLayout([card(60, 900, { fixed: true }), card(60, 900)], {
      ...OPTS,
      twoColumn: false,
    });
    expect(plan.heights).toEqual([null, 500]);
  });
});

describe('split', () => {
  it('matches the old greedy rule when nothing is clipped, then spreads the shortfall', () => {
    // Baseline heights (code order); ceiling is huge so nothing is clipped.
    const measured = [98, 144, 332, 170, 174, 198, 418, 558, 522, 296];
    const cards = measured.map((h) => card(60, h - 60));
    const plan = planLayout(cards, { twoColumn: true, ceiling: 10000, floor: 560, gap: 24 });
    expect(plan.columns).toEqual([
      [0, 2, 5, 7, 9],
      [1, 3, 4, 6, 8],
    ]);
    // Right column is 54 px short: 5 cards, 10 each, the first four get 1 extra.
    expect(plan.heights).toEqual([98, 155, 332, 181, 185, 198, 429, 558, 532, 296]);
    expect(bottoms(plan, cards, 24)).toEqual([1578, 1578]);
  });

  it('a tie goes to the left column', () => {
    const cards = [card(50, 100), card(50, 100), card(50, 100)];
    const plan = planLayout(cards, OPTS);
    expect(plan.columns).toEqual([[0, 2], [1]]);
  });
});

describe('filling the shorter column, in order', () => {
  it('1) grows its clipped cards toward their full content', () => {
    const cards = [card(50, 100), card(50, 700), card(50, 700)];
    const plan = planLayout(cards, OPTS);
    expect(plan.columns).toEqual([[0, 2], [1]]);
    expect(plan.heights).toEqual([150, 660, 500]);
  });

  it('a clipped card never grows past natural; the rest is spread evenly', () => {
    const cards = [card(50, 100), card(50, 550), card(50, 100), card(50, 100), card(50, 200), card(50, 10)];
    const plan = planLayout(cards, OPTS);
    expect(plan.columns).toEqual([
      [0, 2, 3, 4],
      [1, 5],
    ]);
    // Clipped card 1 grows 100 to its natural 600; the remaining 60 splits 30/30.
    expect(plan.heights).toEqual([150, 630, 150, 150, 250, 90]);
    expect(bottoms(plan, cards, 10)).toEqual([730, 730]);
  });

  it('2) grows an elastic card up to 125% of its chart', () => {
    const cards = [card(50, 600), card(50, 400, { elastic: true, minBody: MIN_BODY_CHART })];
    const plan = planLayout(cards, OPTS);
    // D = 500 - 450 = 50; cap = 50 + ceil(400 * 1.25) = 550.
    expect(plan.heights).toEqual([500, 500]);
  });

  it('an elastic card stops at its cap before the spread shares the rest', () => {
    const cards = [card(50, 600), card(50, 100, { elastic: true }), card(50, 100)];
    // Floor == ceiling so the taller column cannot shrink.
    const plan = planLayout(cards, { ...OPTS, floor: 500 });
    expect(plan.columns).toEqual([[0], [1, 2]]);
    // D = 190: elastic +25 (cap 175), then 165 spread as 83 / 82.
    expect(plan.heights).toEqual([500, 258, 232]);
    expect(bottoms(plan, cards, 10)).toEqual([500, 500]);
  });

  it('3) shrinks the taller column before spreading', () => {
    const cards = [card(50, 700), card(50, 430)];
    const plan = planLayout(cards, OPTS);
    // D = 20 and the clipped card has 100 px of room.
    expect(plan.heights).toEqual([480, 480]);
  });

  it('a shrunk card never goes below the floor', () => {
    const cards = [card(50, 700), card(50, 100)];
    const plan = planLayout(cards, OPTS);
    // D = 350; shrink stops at the floor (400), the remaining 250 is spread.
    expect(plan.heights).toEqual([400, 400]);
  });

  it('a shrunk card never goes below overhead + minBody', () => {
    const cards = [card(50, 700, { elastic: true, minBody: 400 }), card(50, 100)];
    const plan = planLayout(cards, OPTS);
    // wanted 500, limit max(400, 450) = 450.
    expect(plan.heights).toEqual([450, 450]);
  });

  it('4) spreads what is left evenly, the odd pixel going to the first card', () => {
    const cards = [card(50, 301), card(50, 50), card(50, 50)];
    const plan = planLayout(cards, OPTS);
    expect(plan.columns).toEqual([[0], [1, 2]]);
    expect(plan.heights).toEqual([351, 171, 170]);
  });
});

describe('fixed cards', () => {
  it('all fixed: legacy behavior, nothing is sized', () => {
    const cards = [card(50, 100, { fixed: true }), card(50, 300, { fixed: true })];
    const plan = planLayout(cards, OPTS);
    expect(plan.columns).toEqual([[0], [1]]);
    expect(plan.heights).toEqual([null, null]);
  });

  it('a fixed card counts at its natural height but is never given one', () => {
    const cards = [card(50, 300), card(50, 100, { fixed: true })];
    const plan = planLayout(cards, OPTS);
    expect(plan.heights).toEqual([350, null]);
  });
});

describe('flush bottoms', () => {
  it.each([5, 7, 9, 10])('is exactly equal for %i random cards (200 iterations)', (count) => {
    const rand = mulberry32(count * 7919);
    const between = (lo: number, hi: number) => lo + Math.floor(rand() * (hi - lo + 1));
    for (let iteration = 0; iteration < 200; iteration++) {
      const cards = Array.from({ length: count }, () =>
        card(between(40, 120), between(20, 900), {
          minBody: between(100, 260),
          elastic: rand() < 0.3,
        }),
      );
      const gap = 24;
      const plan = planLayout(cards, {
        twoColumn: true,
        ceiling: between(560, 800),
        floor: CEILING_FLOOR,
        gap,
      });
      const [left, right] = bottoms(plan, cards, gap);
      expect(left).toBe(right);
      expect(plan.heights.every((h) => h !== null && Number.isInteger(h))).toBe(true);
      expect(plan.columns.flat().sort((a, b) => a - b)).toEqual(cards.map((_, i) => i));
    }
  });

  it('stays within a pixel with a fractional gap and never overshoots', () => {
    const cards = [card(60, 300), card(60, 100), card(60, 100), card(60, 100), card(60, 100)];
    const gap = 22.5;
    const plan = planLayout(cards, { ...OPTS, gap });
    const [left, right] = bottoms(plan, cards, gap);
    expect(Math.abs(left - right)).toBeLessThanOrEqual(1);
    expect(plan.heights.every((h) => h !== null && Number.isInteger(h))).toBe(true);
  });
});

describe('samePlan', () => {
  const base: LayoutPlan = { columns: [[0, 2], [1]], heights: [100, 200, null] };

  it('is true for equal plans', () => {
    expect(samePlan(base, { columns: [[0, 2], [1]], heights: [100, 200, null] })).toBe(true);
  });

  it('is false when one height differs by 1 px', () => {
    expect(samePlan(base, { columns: [[0, 2], [1]], heights: [100, 201, null] })).toBe(false);
  });

  it('is false when null differs from a number, or the columns differ', () => {
    expect(samePlan(base, { columns: [[0, 2], [1]], heights: [100, 200, 0] })).toBe(false);
    expect(samePlan(base, { columns: [[0], [1, 2]], heights: [100, 200, null] })).toBe(false);
  });
});

describe('baseline replays', () => {
  // Code order: Biggest, Upcoming, Top Merchants, Committed, Emergency, Asset Mix,
  // Top Expense, Month-over-Month, Owner Balances, Income Sources.
  const cards: CardMeasure[] = [
    card(60, 38),
    card(60, 84),
    card(60, 272),
    card(60, 110),
    card(60, 114),
    card(60, 138),
    card(98, 320, { elastic: true, minBody: MIN_BODY_CHART }),
    card(78, 752, { elastic: true, minBody: MIN_BODY_CHART }),
    card(102, 598),
    card(60, 236),
  ];
  const OWNER = 8;
  const MOM = 7;

  it('1680x824 (ceiling 577): Owner 595, MoM 577, flush', () => {
    const plan = planLayout(cards, { twoColumn: true, ceiling: ceilingFor(824), floor: 560, gap: 24 });
    expect(plan.columns).toEqual([
      [0, 2, 5, 7, 9],
      [1, 3, 4, 6, 8],
    ]);
    expect(plan.heights[OWNER]).toBe(595);
    expect(plan.heights[MOM]).toBe(577);
    expect(bottoms(plan, cards, 24)).toEqual([1597, 1597]);
  });

  it('1284x714 (ceiling 560): Owner 578, MoM 560, flush', () => {
    const plan = planLayout(cards, { twoColumn: true, ceiling: ceilingFor(714), floor: 560, gap: 24 });
    expect(plan.columns).toEqual([
      [0, 2, 5, 7, 9],
      [1, 3, 4, 6, 8],
    ]);
    expect(plan.heights[OWNER]).toBe(578);
    expect(plan.heights[MOM]).toBe(560);
    expect(bottoms(plan, cards, 24)).toEqual([1580, 1580]);
  });
});
