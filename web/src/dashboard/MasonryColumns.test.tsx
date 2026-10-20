import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import { MasonryColumns } from './MasonryColumns';

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
