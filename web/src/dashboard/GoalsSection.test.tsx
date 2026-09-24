import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { GoalsSection } from './GoalsSection';
import type { GoalItem, GoalsResponse } from '../lib/types';

vi.mock('../lib/queries', () => ({
  useGoals: vi.fn(),
}));

vi.mock('../lib/mutations', () => ({
  useCreateGoal: vi.fn(),
  useDeleteGoal: vi.fn(),
}));

import { useGoals } from '../lib/queries';
import { useCreateGoal, useDeleteGoal } from '../lib/mutations';

const mockedUseGoals = vi.mocked(useGoals);
const mockedUseCreateGoal = vi.mocked(useCreateGoal);
const mockedUseDeleteGoal = vi.mocked(useDeleteGoal);

function goal(overrides: Partial<GoalItem> = {}): GoalItem {
  return {
    id: 1,
    name: 'Down payment',
    target_amount: 80000,
    target_date: '2027-06-01',
    account_keys: ['plaid:savings'],
    saved: 22200,
    pct: 0.2775,
    remaining: 57800,
    monthly_pace: 2150,
    pace_basis: 'cashflow',
    pace_weeks_of_history: 4,
    projected_date: '2028-02-01',
    on_track: false,
    is_complete: false,
    contested_amount: 0,
    ...overrides,
  };
}

function mockGoals(goals: GoalItem[], isPending = false) {
  mockedUseGoals.mockReturnValue({
    data: { goals } as GoalsResponse,
    isPending,
  } as unknown as ReturnType<typeof useGoals>);
}

describe('GoalsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseCreateGoal.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useCreateGoal>);
    mockedUseDeleteGoal.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useDeleteGoal>);
  });

  it('says when there are no goals', () => {
    mockGoals([]);
    render(<GoalsSection />);
    expect(screen.getByText('No goals yet.')).toBeInTheDocument();
  });

  it('renders progress against the target', () => {
    mockGoals([goal()]);
    render(<GoalsSection />);

    expect(screen.getByText('Down payment')).toBeInTheDocument();
    expect(screen.getByText(/\$22,200 of \$80,000/)).toBeInTheDocument();
    expect(screen.getByText(/28%/)).toBeInTheDocument();
  });

  // The rule this component exists to honour: a pace that looks as confident as
  // one built on a year, but rests on four weeks, is worse than showing none.
  it('says a cash-flow pace is a cash-flow pace, and how much history backs it', () => {
    mockGoals([goal({ pace_basis: 'cashflow', pace_weeks_of_history: 4 })]);
    render(<GoalsSection />);

    expect(screen.getByText(/from cash flow \(4 weeks of balance history so far\)/)).toBeInTheDocument();
  });

  it('says when the pace is measured from balances instead', () => {
    mockGoals([goal({ pace_basis: 'balance', pace_weeks_of_history: 16 })]);
    render(<GoalsSection />);

    expect(screen.getByText(/measured from your balances/)).toBeInTheDocument();
    expect(screen.queryByText(/from cash flow/)).not.toBeInTheDocument();
  });

  it('never shows a pace without a basis', () => {
    mockGoals([goal({ pace_basis: 'balance' }), goal({ id: 2, pace_basis: 'cashflow' })]);
    render(<GoalsSection />);

    const paces = screen.getAllByText(/\/mo —/);
    expect(paces).toHaveLength(2);
  });

  // Overlap is allowed because people really do save for two things in one
  // account -- but unsaid, it would let the tab call two goals on track when
  // the same dollars can only buy one.
  it('warns when progress is contested by another goal', () => {
    mockGoals([goal({ contested_amount: 22200 })]);
    render(<GoalsSection />);

    expect(screen.getByText(/another goal also\s+claims/)).toBeInTheDocument();
  });

  it('shows no contested warning when nothing is shared', () => {
    mockGoals([goal({ contested_amount: 0 })]);
    render(<GoalsSection />);

    expect(screen.queryByText(/another goal also/)).not.toBeInTheDocument();
  });

  it('reports on-track, behind and reached distinctly', () => {
    mockGoals([
      goal({ id: 1, on_track: true }),
      goal({ id: 2, on_track: false }),
      goal({ id: 3, is_complete: true, on_track: true }),
    ]);
    render(<GoalsSection />);

    expect(screen.getByText('On track')).toBeInTheDocument();
    expect(screen.getByText('Behind')).toBeInTheDocument();
    expect(screen.getByText('Reached')).toBeInTheDocument();
  });

  it('says so when there is no projection rather than implying one', () => {
    mockGoals([goal({ on_track: null, projected_date: null })]);
    render(<GoalsSection />);

    expect(screen.getByText('No projection yet')).toBeInTheDocument();
  });

  it('creates a goal from the form', async () => {
    const mutate = vi.fn();
    mockedUseCreateGoal.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useCreateGoal>);
    mockGoals([]);

    const user = userEvent.setup();
    render(<GoalsSection />);

    await user.click(screen.getByRole('button', { name: 'Add goal' }));
    await user.type(screen.getByLabelText('Name'), 'Car');
    await user.type(screen.getByLabelText('Target amount'), '15000');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Car', target_amount: 15000 }),
      expect.anything(),
    );
  });

  it('refuses to create a goal with no name or a non-positive target', async () => {
    const mutate = vi.fn();
    mockedUseCreateGoal.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useCreateGoal>);
    mockGoals([]);

    const user = userEvent.setup();
    render(<GoalsSection />);

    await user.click(screen.getByRole('button', { name: 'Add goal' }));
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(mutate).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText('Name'), 'Car');
    await user.type(screen.getByLabelText('Target amount'), '0');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(mutate).not.toHaveBeenCalled();
  });
});
