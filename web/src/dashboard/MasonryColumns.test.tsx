import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { MasonryColumns, ScrollBody, Stack } from './MasonryColumns';

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation(() => ({
      matches,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

/** Fake observer that behaves like a browser's: it only fires for elements it
 *  is still observing AND that are still in the document. A detached node
 *  cannot change size, so a real observer watching only detached nodes never
 *  fires -- which is exactly the original bug, and why `trigger()` must not
 *  simply call every callback. */
class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  static observed: Element[] = [];
  static fireOnObserve = false;
  static calls = 0;
  private cb: () => void;
  private elements: Element[] = [];
  constructor(cb: () => void) {
    this.cb = cb;
    FakeResizeObserver.instances.push(this);
  }
  observe(el: Element) {
    this.elements.push(el);
    FakeResizeObserver.observed.push(el);
    if (FakeResizeObserver.fireOnObserve) {
      FakeResizeObserver.calls++;
      this.cb();
    }
  }
  unobserve() {}
  disconnect() {
    this.elements = [];
  }
  static reset() {
    FakeResizeObserver.instances = [];
    FakeResizeObserver.observed = [];
    FakeResizeObserver.fireOnObserve = false;
    FakeResizeObserver.calls = 0;
  }
  /** A size change on one element: only observers watching THAT element fire. */
  static resize(el: Element) {
    FakeResizeObserver.instances
      .filter((i) => document.body.contains(el) && i.elements.includes(el))
      .forEach((i) => i.cb());
  }
}

/** Heights are looked up by the `data-height` key on the wrapper's first child. */
let heights: Record<string, number> = {};
function mockHeights() {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const child = this.firstElementChild as HTMLElement | null;
    const key = child?.dataset.height;
    return { height: key ? (heights[key] ?? 0) : 0 } as DOMRect;
  });
}

function cards(ids: string[]) {
  return ids.map((id) => (
    <div key={id} data-height={id}>
      {id}
    </div>
  ));
}

/** The children of the outer flex container: columns (two-column) or wrappers (stacked). */
function childrenOfRoot(container: HTMLElement): HTMLElement[] {
  return Array.from(container.firstElementChild!.children) as HTMLElement[];
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  FakeResizeObserver.reset();
  heights = {};
});

describe('MasonryColumns', () => {
  it('renders every child', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>);
    for (const id of ['A', 'B', 'C', 'D']) expect(screen.getByText(id)).toBeInTheDocument();
  });

  it('stacks everything in one column, in order, below lg', () => {
    stubMatchMedia(false);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    const { container } = render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>);
    const wrappers = childrenOfRoot(container);
    expect(wrappers.map((w) => w.textContent)).toEqual(['A', 'B', 'C', 'D']);
    expect(container.firstElementChild).not.toHaveClass('lg:flex-row');
  });

  it('renders two columns at lg', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    const { container } = render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>);
    expect(container.firstElementChild).toHaveClass('lg:flex-row');
    expect(childrenOfRoot(container)).toHaveLength(2);
  });

  it('survives a missing ResizeObserver', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', undefined);
    expect(() => render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>)).not.toThrow();
    for (const id of ['A', 'B', 'C', 'D']) expect(screen.getByText(id)).toBeInTheDocument();
  });

  it('balances by measured height', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    heights = { A: 300, B: 100, C: 100, D: 100 };
    mockHeights();
    const { container } = render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>);
    const cols = childrenOfRoot(container);
    const sums = cols.map((c) =>
      Array.from(c.children).reduce(
        (s, w) => s + heights[(w.firstElementChild as HTMLElement).dataset.height!],
        0,
      ),
    );
    expect(Math.abs(sums[0] - sums[1])).toBeLessThanOrEqual(300);
    const colWithA = cols.find((c) => within(c).queryByText('A'))!;
    const others = ['B', 'C', 'D'].filter((id) => within(colWithA).queryByText(id));
    expect(others).not.toHaveLength(3);
    expect(sums).toEqual([300, 300]);
  });

  // The regression test. React reconciles children by key WITHIN a parent, so
  // when the columns are assigned, a card that stays in the left column keeps
  // its DOM node, but a card that moves to the right column gets a new one. The
  // original component attached its observer once, before that move, so it kept
  // watching the left column's cards and never saw the right column's: a card
  // on the right growing (data arriving, a refetch) never re-balanced, and the
  // two columns' bottoms drifted apart. B lands in the right column here.
  it('re-balances when a card in the right-hand column changes height', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    heights = { A: 100, B: 100, C: 100, D: 100 };
    mockHeights();
    const { container } = render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>);
    expect(childrenOfRoot(container).map((c) => c.textContent)).toEqual(['AC', 'BD']);

    heights = { A: 100, B: 300, C: 100, D: 100 };
    act(() => FakeResizeObserver.resize(screen.getByText('B').parentElement!));

    expect(childrenOfRoot(container).map((c) => c.textContent)).toEqual(['ACD', 'B']);
  });

  it('only ever observes nodes that are still in the document', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    heights = { A: 100, B: 100, C: 100, D: 100 };
    mockHeights();
    render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>);

    const live = FakeResizeObserver.instances.at(-1)!;
    const watched = FakeResizeObserver.observed.slice(-4);
    expect(live).toBeDefined();
    expect(watched).toHaveLength(4);
    for (const el of watched) expect(document.body.contains(el)).toBe(true);
  });

  it('does not loop when observe() fires its callback immediately', () => {
    stubMatchMedia(true);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    FakeResizeObserver.fireOnObserve = true;
    heights = { A: 300, B: 100, C: 100, D: 100 };
    mockHeights();
    expect(() => render(<MasonryColumns>{cards(['A', 'B', 'C', 'D'])}</MasonryColumns>)).not.toThrow();
    expect(FakeResizeObserver.calls).toBeLessThan(50);
    expect(screen.getByText('A')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Phase 36: cards that register a ScrollBody are sized by the planner.
// ---------------------------------------------------------------------------

/** Row height per card id, read by the layout mock; tests mutate it to "resize" rows. */
let rowHeights: Record<string, number> = {};

interface ScrollCardProps {
  id: string;
  overhead: number;
  rows?: number;
  elastic?: number;
}

/** A pool card: a fixed header (`overhead` px) above a ScrollBody. */
function ScrollCard({ id, overhead, rows = 0, elastic }: ScrollCardProps) {
  return (
    <div data-card={id} data-overhead={overhead}>
      <ScrollBody elasticHeight={elastic}>
        {elastic !== undefined ? (
          <div>{id} chart</div>
        ) : (
          <Stack>
            {Array.from({ length: rows }, (_, k) => (
              <div key={k} data-row={id}>
                {id}
                {k}
              </div>
            ))}
          </Stack>
        )}
      </ScrollBody>
    </div>
  );
}

/** The card element directly inside a pool wrapper, if `el` is a wrapper. */
function cardIn(el: Element | null): HTMLElement | null {
  const first = el?.firstElementChild as HTMLElement | null | undefined;
  return first?.dataset.card ? first : null;
}

/** jsdom does no layout, so model it: a row is `rowHeights[id]` tall; a wrapper is
 *  its inline height if the planner set one, else header + natural content; the
 *  scroll body's clientHeight is the wrapper minus the header. */
function mockLayout() {
  const natural = (cardEl: HTMLElement) => {
    const id = cardEl.dataset.card!;
    const rows = cardEl.querySelectorAll('[data-row]').length;
    const chart = cardEl.querySelector('[style*="min-height"]') as HTMLElement | null;
    const content = chart ? parseFloat(chart.style.minHeight) : rows * (rowHeights[id] ?? 0);
    return Number(cardEl.dataset.overhead) + content;
  };
  const wrapperHeight = (wrapper: HTMLElement) =>
    wrapper.style.height ? parseFloat(wrapper.style.height) : natural(cardIn(wrapper)!);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    if (this.dataset.row) return { height: rowHeights[this.dataset.row] ?? 0 } as DOMRect;
    if (cardIn(this)) return { height: wrapperHeight(this) } as DOMRect;
    return { height: 0 } as DOMRect;
  });
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (this: HTMLElement) {
    if (!this.className.includes('overflow-y-auto')) return 0;
    const cardEl = this.closest('[data-card]') as HTMLElement;
    return wrapperHeight(cardEl.parentElement!) - Number(cardEl.dataset.overhead);
  });
}

function wrapperOf(id: string): HTMLElement {
  return (document.querySelector(`[data-card="${id}"]`) as HTMLElement).parentElement!;
}

function heightOf(id: string): number {
  return parseFloat(wrapperOf(id).style.height);
}

/** jsdom's innerHeight is 768, so the ceiling is max(538, 560) = 560.
 *  A: 60 + 12 x 50 = 660 natural -> clipped to 560. B, C: 160. D: 110.
 *  Split: A left; B, C, D right (430). Right is 130 short with nothing to
 *  grow or shrink, so it's spread: B +44, C +43, D +43. */
function pool(bRows = 2) {
  return (
    <MasonryColumns>
      <ScrollCard key="A" id="A" overhead={60} rows={12} />
      <ScrollCard key="B" id="B" overhead={60} rows={bRows} />
      <ScrollCard key="C" id="C" overhead={60} rows={2} />
      <ScrollCard key="D" id="D" overhead={60} rows={1} />
    </MasonryColumns>
  );
}

describe('MasonryColumns sizing (ScrollBody cards)', () => {
  function setup(twoColumn = true) {
    stubMatchMedia(twoColumn);
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    rowHeights = { A: 50, B: 50, C: 50, D: 50 };
    mockLayout();
  }

  afterEach(() => {
    rowHeights = {};
  });

  it('gives each wrapper its planned height, and the columns end flush', () => {
    setup();
    render(pool());
    expect(heightOf('A')).toBe(560);
    expect([heightOf('B'), heightOf('C'), heightOf('D')]).toEqual([204, 203, 153]);
    expect(heightOf('B') + heightOf('C') + heightOf('D')).toBe(heightOf('A'));
  });

  it('stacked: wanted heights in order, no stretching', () => {
    setup(false);
    render(pool());
    expect(['A', 'B', 'C', 'D'].map(heightOf)).toEqual([560, 160, 160, 110]);
  });

  it('measures content from the Stack rows, so re-measuring a sized layout changes nothing', async () => {
    setup();
    render(pool());
    const before = ['A', 'B', 'C', 'D'].map(heightOf);
    await act(async () => {
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => requestAnimationFrame(resolve));
    });
    expect(['A', 'B', 'C', 'D'].map(heightOf)).toEqual(before);
  });

  it('observes the Stack rows, never the sized wrappers, and re-plans when a row grows', () => {
    setup();
    render(pool());
    const observed = new Set(FakeResizeObserver.observed);
    expect(['A', 'B', 'C', 'D'].some((id) => observed.has(wrapperOf(id)))).toBe(false);
    const row = document.querySelector('[data-row="D"]')!;
    expect(observed.has(row)).toBe(true);

    // D's single row grows by 100: the right column is now 530 natural
    // against A's 560, so only 30 is spread (B +10, C +10, D +10).
    rowHeights = { ...rowHeights, D: 150 };
    act(() => FakeResizeObserver.resize(row));
    expect(heightOf('B') + heightOf('C') + heightOf('D')).toBe(560);
    expect(heightOf('D')).toBe(220);
  });

  it('re-plans when a refetch adds rows (MutationObserver)', async () => {
    setup();
    const { rerender } = render(pool());
    expect(heightOf('B')).toBe(204);
    rerender(pool(4));
    // B is now 260 natural: right = 260 + 160 + 110 = 530, 30 short of A.
    await waitFor(() => expect(heightOf('B')).toBe(270));
    expect(heightOf('B') + heightOf('C') + heightOf('D')).toBe(560);
  });

  it('an elastic body fills its card but never compresses below the chart height', () => {
    setup();
    render(
      <MasonryColumns>
        <ScrollCard key="A" id="A" overhead={60} rows={2} />
        <ScrollCard key="E" id="E" overhead={60} elastic={300} />
      </MasonryColumns>,
    );
    const inner = document.querySelector('[data-card="E"] .overflow-y-auto')!
      .firstElementChild as HTMLElement;
    expect(inner.style.height).toBe('100%');
    expect(inner.style.minHeight).toBe('300px');
  });

  it('re-clips when the viewport height changes, once per animation frame', async () => {
    setup();
    render(pool());
    expect(heightOf('A')).toBe(560);
    const original = window.innerHeight;
    Object.defineProperty(window, 'innerHeight', { value: 1000, configurable: true });
    try {
      // Ceiling 700: A shows all 660, after the coalesced frame.
      act(() => {
        window.dispatchEvent(new Event('resize'));
        window.dispatchEvent(new Event('resize'));
      });
      expect(heightOf('A')).toBe(560);
      await waitFor(() => expect(heightOf('A')).toBe(660));
    } finally {
      Object.defineProperty(window, 'innerHeight', { value: original, configurable: true });
    }
  });

  it('does not loop when observe() fires its callback immediately', () => {
    setup();
    FakeResizeObserver.fireOnObserve = true;
    expect(() => render(pool())).not.toThrow();
    expect(FakeResizeObserver.calls).toBeLessThan(100);
    expect(heightOf('A')).toBe(560);
  });
});

describe('ScrollBody and Stack outside MasonryColumns', () => {
  it('give an elastic chart its natural height instead of collapsing it', () => {
    const { container } = render(
      <ScrollBody elasticHeight={300}>
        <div>chart</div>
      </ScrollBody>,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.style.height).toBe('300px');
    expect(container.querySelector('.overflow-y-auto')).toBeNull();
  });

  it('render the rows as a plain column, with no scroll wrapper or even spacing', () => {
    const { container } = render(
      <ScrollBody>
        <Stack as="ul">
          <li>one</li>
          <li>two</li>
        </Stack>
      </ScrollBody>,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.tagName).toBe('UL');
    expect(root).toHaveClass('flex', 'flex-col', 'gap-1.5');
    expect(root).not.toHaveClass('justify-evenly');
    expect(container.querySelector('.overflow-y-auto')).toBeNull();
  });
});
