import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { AuthProvider } from './auth/AuthContext';
import { apiFetch, UnauthorizedError } from './lib/api';

// Mock the fetch wrapper directly rather than the raw `fetch` global — this
// is the seam the plan calls out (vi.mock over msw for this phase's scope):
// every query/mutation in the app goes through `apiFetch`, so mocking it
// here exercises the real AuthProvider/App wiring without needing a network
// layer.
vi.mock('./lib/api', async () => {
  const actual = await vi.importActual<typeof import('./lib/api')>('./lib/api');
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

const mockedApiFetch = vi.mocked(apiFetch);

function renderApp() {
  // A fresh QueryClient per test avoids cross-test cache bleed; retries are
  // disabled so tests don't wait through the real backoff schedule.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe('auth flow', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it('renders the sign-in page with a link to the Google OAuth start endpoint when unauthenticated', async () => {
    mockedApiFetch.mockRejectedValue(new UnauthorizedError());

    renderApp();

    const link = await screen.findByRole('link', { name: /sign in with google/i });
    expect(link).toHaveAttribute('href', expect.stringContaining('/auth/google/start'));
  });

  it('renders the authenticated shell when /auth/me succeeds', async () => {
    mockedApiFetch.mockResolvedValue({
      email: 'user@example.com',
      name: 'Test User',
      picture: null,
      csrf_token: 'test-csrf-token',
    });

    renderApp();

    expect(await screen.findByText(/signed in as user@example.com/i)).toBeInTheDocument();
  });

  it('falls back to the sign-in page when a subsequent call 401s after being authenticated', async () => {
    mockedApiFetch.mockResolvedValue({
      email: 'user@example.com',
      name: 'Test User',
      picture: null,
      csrf_token: 'test-csrf-token',
    });

    renderApp();

    expect(await screen.findByText(/signed in as user@example.com/i)).toBeInTheDocument();

    // Simulate a later API call (e.g. a data fetch in R4) getting a 401 —
    // apiFetch itself calls notifyUnauthorized() before throwing, so the
    // next /auth/me refetch reflects that here too.
    mockedApiFetch.mockRejectedValue(new UnauthorizedError());
    const { notifyUnauthorized } = await import('./lib/authStore');
    notifyUnauthorized();

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /sign in with google/i })).toBeInTheDocument();
    });
  });

  // Guards the `notifyUnauthorized -> resetQueries` path against becoming self-perpetuating.
  // The other tests mock apiFetch wholesale, so notifyUnauthorized() never fires in them;
  // this one reproduces the real side effect (apiFetch calls it before throwing) and asserts
  // the app still settles on sign-in with a bounded number of fetches.
  it('settles on the sign-in page with bounded fetches when the first /auth/me 401s', async () => {
    const { notifyUnauthorized } = await import('./lib/authStore');
    mockedApiFetch.mockImplementation(async () => {
      notifyUnauthorized();
      throw new UnauthorizedError();
    });

    renderApp();

    expect(await screen.findByRole('link', { name: /sign in with google/i })).toBeInTheDocument();

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(mockedApiFetch.mock.calls.length).toBeLessThanOrEqual(2);
  });
});
