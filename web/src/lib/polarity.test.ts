import { describe, it, expect } from 'vitest';
import {
  DEFAULT_POLARITY,
  DIRECTION_GLYPH,
  METRIC_POLARITY,
  TONE_TOKENS,
  directionOf,
  polarityOf,
  toneFor,
  toneForMetric,
  toneLabel,
  type Polarity,
  type Tone,
} from './polarity';

describe('polarityOf', () => {
  it('marks earning metrics as normal (up is good)', () => {
    expect(polarityOf('avg_monthly_income')).toBe('normal');
    expect(polarityOf('savings_rate')).toBe('normal');
    expect(polarityOf('net_worth')).toBe('normal');
  });

  it('marks spending and debt metrics as inverse (up is bad)', () => {
    expect(polarityOf('avg_monthly_expense')).toBe('inverse');
    expect(polarityOf('credit_utilization')).toBe('inverse');
    expect(polarityOf('liabilities')).toBe('inverse');
    expect(polarityOf('rolling_30d_spend')).toBe('inverse');
  });

  it('marks counting metrics as neutral', () => {
    expect(polarityOf('transaction_count')).toBe('neutral');
  });

  it('falls back to neutral rather than guessing for unknown or missing keys', () => {
    expect(polarityOf('some_new_api_field')).toBe(DEFAULT_POLARITY);
    expect(polarityOf('')).toBe(DEFAULT_POLARITY);
    expect(polarityOf(null)).toBe(DEFAULT_POLARITY);
    expect(polarityOf(undefined)).toBe(DEFAULT_POLARITY);
  });

  it('does not inherit anything from Object.prototype', () => {
    expect(polarityOf('toString')).toBe(DEFAULT_POLARITY);
    expect(polarityOf('constructor')).toBe(DEFAULT_POLARITY);
  });
});

describe('directionOf', () => {
  it('reads the sign of the delta', () => {
    expect(directionOf(12)).toBe('up');
    expect(directionOf(-12)).toBe('down');
    expect(directionOf(0)).toBe('flat');
  });

  it('treats missing and non-finite deltas as flat', () => {
    expect(directionOf(null)).toBe('flat');
    expect(directionOf(undefined)).toBe('flat');
    expect(directionOf(NaN)).toBe('flat');
    expect(directionOf(Infinity)).toBe('flat');
  });

  it('collapses noise inside epsilon to flat', () => {
    expect(directionOf(0.004, 0.005)).toBe('flat');
    expect(directionOf(-0.004, 0.005)).toBe('flat');
    expect(directionOf(0.006, 0.005)).toBe('up');
  });
});

describe('toneFor -- the polarity matrix', () => {
  const cases: [Polarity, number, Tone][] = [
    ['normal', 1, 'good'],
    ['normal', -1, 'bad'],
    ['normal', 0, 'neutral'],
    ['inverse', 1, 'bad'],
    ['inverse', -1, 'good'],
    ['inverse', 0, 'neutral'],
    ['neutral', 1, 'neutral'],
    ['neutral', -1, 'neutral'],
    ['neutral', 0, 'neutral'],
  ];

  it.each(cases)('%s polarity with delta %d -> %s', (polarity, delta, expected) => {
    expect(toneFor(delta, polarity)).toBe(expected);
  });

  it('gives the same delta opposite tones under opposite polarity', () => {
    // The entire point of the module: +$400 is not one colour.
    expect(toneFor(400, 'normal')).toBe('good');
    expect(toneFor(400, 'inverse')).toBe('bad');
    expect(toneFor(-400, 'normal')).toBe('bad');
    expect(toneFor(-400, 'inverse')).toBe('good');
  });

  it('is neutral for a missing delta whatever the polarity', () => {
    expect(toneFor(null, 'normal')).toBe('neutral');
    expect(toneFor(undefined, 'inverse')).toBe('neutral');
    expect(toneFor(NaN, 'normal')).toBe('neutral');
  });

  it('honours epsilon', () => {
    expect(toneFor(0.001, 'inverse', 0.01)).toBe('neutral');
    expect(toneFor(0.02, 'inverse', 0.01)).toBe('bad');
  });
});

describe('toneForMetric', () => {
  it('does not paint a bigger expense and a bigger surplus the same colour', () => {
    // The bug Fix 11 exists to remove.
    expect(toneForMetric('avg_monthly_expense', 400)).toBe('bad');
    expect(toneForMetric('net_flow', 400)).toBe('good');
  });

  it('reads a falling credit utilisation as good', () => {
    expect(toneForMetric('credit_utilization', -0.05)).toBe('good');
  });

  it('reads a rising savings rate as good', () => {
    expect(toneForMetric('savings_rate', 0.03)).toBe('good');
  });

  it('leaves unknown metrics unvalenced', () => {
    expect(toneForMetric('mystery_metric', 999)).toBe('neutral');
  });
});

describe('token and label mapping', () => {
  it('maps every tone to a distinct fill and a distinct text token', () => {
    const fills = Object.values(TONE_TOKENS).map((t) => t.fill);
    const texts = Object.values(TONE_TOKENS).map((t) => t.text);
    expect(new Set(fills).size).toBe(fills.length);
    expect(new Set(texts).size).toBe(texts.length);
  });

  it('keeps semantic tokens disjoint from the categorical slots', () => {
    const all = Object.values(TONE_TOKENS).flatMap((t) => [t.fill, t.text]);
    for (const token of all) {
      expect(token).not.toMatch(/--cat-/);
      expect(token).not.toMatch(/--seq-/);
    }
  });

  it('offers a glyph for every direction so colour never stands alone', () => {
    expect(DIRECTION_GLYPH.up).toBeTruthy();
    expect(DIRECTION_GLYPH.down).toBeTruthy();
    expect(DIRECTION_GLYPH.flat).toBeTruthy();
  });

  it('labels a delta in words, not just colour', () => {
    expect(toneLabel('up', 'good')).toBe('up (better)');
    expect(toneLabel('up', 'bad')).toBe('up (worse)');
    expect(toneLabel('down', 'good')).toBe('down (better)');
    expect(toneLabel('down', 'neutral')).toBe('down');
    expect(toneLabel('flat', 'neutral')).toBe('unchanged');
  });
});

describe('METRIC_POLARITY table', () => {
  it('is frozen so no component can redefine a metric mid-session', () => {
    expect(Object.isFrozen(METRIC_POLARITY)).toBe(true);
  });

  it('only contains valid polarity values', () => {
    for (const value of Object.values(METRIC_POLARITY)) {
      expect(['normal', 'inverse', 'neutral']).toContain(value);
    }
  });
});

describe('every metric key the API actually emits has a polarity', () => {
  // These are the exact field names in `api/routers/data.py`'s view models. A key that
  // does not match falls back to 'neutral', which renders a grey badge on a metric with
  // an obvious direction -- a silent presentation bug, not an error.
  it.each([
    ['net_worth', 'normal'],
    ['total_assets', 'normal'],
    ['total_liabilities', 'inverse'],
    ['savings_rate', 'normal'],
    ['avg_monthly_income', 'normal'],
    ['avg_monthly_expense', 'inverse'],
    ['avg_monthly_net', 'normal'],
    ['avg_weekly_income', 'normal'],
    ['avg_weekly_expense', 'inverse'],
    ['emergency_fund_months', 'normal'],
  ])('%s is %s', (key, expected) => {
    expect(polarityOf(key)).toBe(expected);
  });
});
