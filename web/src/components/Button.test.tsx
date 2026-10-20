import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button, BUTTON_BASE_CLASSES } from './Button';

describe('Button', () => {
  it('renders a type="button" by default so it never submits a surrounding form', () => {
    render(<Button>Clear all</Button>);
    expect(screen.getByRole('button', { name: 'Clear all' })).toHaveAttribute('type', 'button');
  });

  it('honours an explicit type', () => {
    render(<Button type="submit">Save</Button>);
    expect(screen.getByRole('button', { name: 'Save' })).toHaveAttribute('type', 'submit');
  });

  it('forwards clicks', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Clear all</Button>);

    await user.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire when disabled', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        Clear all
      </Button>,
    );

    await user.click(screen.getByRole('button', { name: 'Clear all' }));
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Clear all' })).toBeDisabled();
  });

  // The whole point of extracting this component: every variant carries the
  // affordance classes, so a new button cannot silently ship without them.
  it.each(['primary', 'secondary', 'ghost', 'danger'] as const)(
    'variant %s carries cursor, focus-visible and disabled affordances',
    (variant) => {
      render(<Button variant={variant}>Go</Button>);
      const className = screen.getByRole('button', { name: 'Go' }).className;

      expect(className).toContain('cursor-pointer');
      expect(className).toContain('focus-visible:ring-2');
      expect(className).toContain('disabled:cursor-not-allowed');
      expect(className).toContain('hover:');
    },
  );

  it.each(['primary', 'secondary', 'ghost', 'danger'] as const)(
    'variant %s produces a distinct class string',
    (variant) => {
      const { unmount } = render(<Button variant={variant}>Go</Button>);
      const own = screen.getByRole('button', { name: 'Go' }).className;
      unmount();

      render(<Button>Go</Button>);
      const fallback = screen.getByRole('button', { name: 'Go' }).className;

      if (variant === 'secondary') {
        expect(own).toBe(fallback); // secondary is the default
      } else {
        expect(own).not.toBe(fallback);
      }
    },
  );

  it('appends caller classes rather than replacing the variant', () => {
    render(<Button className="w-full">Go</Button>);
    const className = screen.getByRole('button', { name: 'Go' }).className;

    expect(className).toContain('w-full');
    expect(className).toContain('cursor-pointer');
  });

  it('spreads arbitrary button props', () => {
    render(
      <Button aria-expanded={false} aria-haspopup="dialog">
        More filters
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'More filters' });

    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAttribute('aria-haspopup', 'dialog');
  });

  it('exports base classes that already include the affordances', () => {
    expect(BUTTON_BASE_CLASSES).toContain('cursor-pointer');
    expect(BUTTON_BASE_CLASSES).toContain('disabled:cursor-not-allowed');
  });
});
