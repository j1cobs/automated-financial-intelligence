import { describe, it, expect } from 'vitest';
import { strings } from './strings';

describe('strings.metricTile.baselineComparison', () => {
  it('renders "above" for a positive delta', () => {
    expect(strings.metricTile.baselineComparison(0.12, 3)).toBe('12% above your 3-month average');
  });

  it('renders "below" for a negative delta', () => {
    expect(strings.metricTile.baselineComparison(-0.08, 6)).toBe('8% below your 6-month average');
  });

  it('renders "at" (no percent) when the delta rounds to zero', () => {
    expect(strings.metricTile.baselineComparison(0, 3)).toBe('at your 3-month average');
    expect(strings.metricTile.baselineComparison(0.001, 3)).toBe('at your 3-month average');
  });

  it('uses singular "month" for a 1-month baseline', () => {
    expect(strings.metricTile.baselineComparison(0.2, 1)).toBe('20% above your 1-month average');
  });

  it('rounds the percentage to the nearest whole number', () => {
    expect(strings.metricTile.baselineComparison(0.1538, 3)).toBe('15% above your 3-month average');
  });
});

describe('strings.metricTile.infoButtonLabel', () => {
  it('names the metric in the accessible label', () => {
    expect(strings.metricTile.infoButtonLabel('Net Worth')).toBe('More about Net Worth');
  });
});
