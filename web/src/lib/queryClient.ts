import { QueryClient, QueryCache } from '@tanstack/react-query';
import { UnauthorizedError } from './api';

/**
 * Exponential backoff capped at 30s, e.g. 1s, 2s, 4s, 8s, 16s, 30s, 30s, ...
 * This is what makes the Render free-tier cold start (can be 30s+) tolerable:
 * a query keeps retrying quietly instead of surfacing a hard failure after
 * the first attempt.
 */
export function backoffDelay(attemptIndex: number): number {
  return Math.min(1000 * 2 ** attemptIndex, 30_000);
}

/**
 * A 401 is a definitive answer ("not authenticated"), not a transient
 * failure — retrying it wastes time and delays showing the sign-in page.
 * Everything else (network errors, 5xx, a cold-start timeout) is worth
 * retrying with backoff.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof UnauthorizedError) return false;
  return failureCount < 6;
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      // UnauthorizedError already triggers authStore's notifyUnauthorized()
      // inside apiFetch, which AuthProvider subscribes to — nothing else to
      // do here besides letting the error propagate to each query's own
      // state (isError/error) for callers that want to render it directly.
      void error;
    },
  }),
  defaultOptions: {
    queries: {
      retry: shouldRetry,
      retryDelay: backoffDelay,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
