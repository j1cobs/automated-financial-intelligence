import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TabSkeleton, ErrorState } from './LoadingState';

describe('TabSkeleton', () => {
  it('renders an accessible loading region', () => {
    render(<TabSkeleton />);
    expect(screen.getByRole('status', { name: 'Loading…' })).toBeInTheDocument();
  });

  it('renders layout-shaped placeholder blocks', () => {
    const { container } = render(<TabSkeleton />);
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(1);
  });
});

describe('ErrorState', () => {
  it('renders the given message', () => {
    render(<ErrorState message="Something broke." />);
    expect(screen.getByRole('alert')).toHaveTextContent('Something broke.');
  });

  it('calls onRetry when the retry button is clicked', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Something broke." onRetry={onRetry} />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('omits the retry button when onRetry is not provided', () => {
    render(<ErrorState message="Something broke." />);
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });
});
