import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MultiSelectPopover, type MultiSelectOption } from './MultiSelectPopover';

const FEW_OPTIONS: MultiSelectOption[] = [
  { value: 'a', label: 'Alice' },
  { value: 'b', label: 'Bob' },
  { value: 'c', label: 'Carol' },
];

// Above the component's SEARCH_THRESHOLD (6), so the search field renders.
const MANY_OPTIONS: MultiSelectOption[] = ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank', 'Grace'].map(
  (label) => ({ value: label, label }),
);

function renderPopover(
  options: MultiSelectOption[],
  selected: string[] | null = null,
  onChange: (values: string[] | null) => void = vi.fn(),
) {
  return render(
    <MultiSelectPopover
      id="test-field"
      label="Owner"
      options={options}
      selected={selected}
      onChange={onChange}
    />,
  );
}

describe('MultiSelectPopover', () => {
  it('closed by default; opens the checkbox list on trigger click', async () => {
    const user = userEvent.setup();
    renderPopover(FEW_OPTIONS);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByLabelText('Owner'));

    const dialog = screen.getByRole('dialog', { name: 'Owner' });
    expect(within(dialog).getByRole('checkbox', { name: 'Alice' })).toBeInTheDocument();
    expect(within(dialog).getByRole('checkbox', { name: 'Bob' })).toBeInTheDocument();
    expect(within(dialog).getByRole('checkbox', { name: 'Carol' })).toBeInTheDocument();
  });

  it('shows the selected count on the trigger', async () => {
    renderPopover(FEW_OPTIONS, ['a', 'b']);
    expect(screen.getByRole('button', { name: 'Owner (2)' })).toBeInTheDocument();
  });

  it('checking an option calls onChange with it added', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPopover(FEW_OPTIONS, ['a'], onChange);

    await user.click(screen.getByRole('button', { name: /^Owner/ }));
    await user.click(screen.getByRole('checkbox', { name: 'Bob' }));

    expect(onChange).toHaveBeenCalledWith(['a', 'b']);
  });

  it('unchecking the only selected option calls onChange with null', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPopover(FEW_OPTIONS, ['a'], onChange);

    await user.click(screen.getByRole('button', { name: /^Owner/ }));
    await user.click(screen.getByRole('checkbox', { name: 'Alice' }));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('"Select all" selects every currently-filtered option', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPopover(FEW_OPTIONS, null, onChange);

    await user.click(screen.getByLabelText('Owner'));
    await user.click(screen.getByRole('button', { name: 'Select all' }));

    expect(onChange).toHaveBeenCalledWith(['a', 'b', 'c']);
  });

  it('"Clear" calls onChange with null', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPopover(FEW_OPTIONS, ['a', 'b'], onChange);

    await user.click(screen.getByRole('button', { name: /^Owner/ }));
    await user.click(screen.getByRole('button', { name: 'Clear' }));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('has no search field when options are few', async () => {
    const user = userEvent.setup();
    renderPopover(FEW_OPTIONS);
    await user.click(screen.getByLabelText('Owner'));
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
  });

  it('search filters the checkbox list by label, case-insensitively', async () => {
    const user = userEvent.setup();
    renderPopover(MANY_OPTIONS);

    await user.click(screen.getByLabelText('Owner'));
    const dialog = screen.getByRole('dialog', { name: 'Owner' });
    const search = within(dialog).getByRole('searchbox');
    await user.type(search, 'ra');

    expect(within(dialog).getByRole('checkbox', { name: 'Frank' })).toBeInTheDocument();
    expect(within(dialog).getByRole('checkbox', { name: 'Grace' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('checkbox', { name: 'Alice' })).not.toBeInTheDocument();
  });

  it('"Select all" while filtered only selects the filtered subset, keeping prior selections', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderPopover(MANY_OPTIONS, ['Dave'], onChange);

    await user.click(screen.getByRole('button', { name: /^Owner/ }));
    const dialog = screen.getByRole('dialog', { name: 'Owner' });
    await user.type(within(dialog).getByRole('searchbox'), 'ra');
    await user.click(within(dialog).getByRole('button', { name: 'Select all' }));

    expect(onChange).toHaveBeenCalledWith(['Dave', 'Frank', 'Grace']);
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup();
    renderPopover(FEW_OPTIONS);

    const trigger = screen.getByLabelText('Owner');
    await user.click(trigger);
    expect(screen.getByRole('dialog', { name: 'Owner' })).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('closes on an outside click', async () => {
    const user = userEvent.setup();
    render(
      <div>
        <MultiSelectPopover
          id="test-field"
          label="Owner"
          options={FEW_OPTIONS}
          selected={null}
          onChange={vi.fn()}
        />
        <button type="button">Outside</button>
      </div>,
    );

    await user.click(screen.getByLabelText('Owner'));
    expect(screen.getByRole('dialog', { name: 'Owner' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Outside' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
