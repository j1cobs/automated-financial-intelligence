import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { setCsrfToken, onUnauthorized } from '../lib/authStore';

export interface AuthUser {
  email: string;
  name: string | null;
  picture: string | null;
}

interface MeResponse {
  email: string;
  name: string | null;
  picture: string | null;
  csrf_token: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  csrfToken: string | null;
  /** True on the initial check, and for every cold-start retry in flight. */
  isLoading: boolean;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AUTH_ME_QUERY_KEY = ['auth', 'me'] as const;

async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/auth/me');
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: AUTH_ME_QUERY_KEY,
    queryFn: fetchMe,
    // A 401 here is a real "not signed in" answer — don't treat it as stale
    // forever, but don't hammer the API either.
    staleTime: 5 * 60 * 1000,
  });

  // A 401 from ANY api call (not just this query) means the session expired
  // — re-run the /auth/me check so the app falls back to the sign-in page.
  useEffect(() => {
    return onUnauthorized(() => {
      setCsrfToken(null);
      // Only act when we currently hold a session. If /auth/me *itself* just 401'd there is
      // nothing to invalidate — its own error state already routes the app to the sign-in
      // page — and resetting here would refetch it, 401 again, fire this listener again, and
      // loop forever, pinning `isFetching` true so App never leaves <LoadingScreen />.
      // `resetQueries` (not `setQueryData(undefined)`, which is a no-op — an `undefined`
      // update is ignored by TanStack Query) both purges the cached user and refetches in one
      // step; the purge is what makes the follow-up 401 find no data and stop the cycle.
      if (queryClient.getQueryData(AUTH_ME_QUERY_KEY) !== undefined) {
        queryClient.resetQueries({ queryKey: AUTH_ME_QUERY_KEY });
      }
    });
  }, [queryClient]);

  useEffect(() => {
    if (query.data) {
      setCsrfToken(query.data.csrf_token);
    } else if (query.isError) {
      setCsrfToken(null);
    }
  }, [query.data, query.isError]);

  // v5's `isLoading` is `isPending && isFetching` — true for the genuine first load *and*
  // every cold-start retry (no data yet, request in flight), false once the query settles
  // (success, or a 401 that won't be retried — see `shouldRetry` in queryClient.ts).
  // Deliberately NOT `isPending || isFetching`: that form also goes true for *background*
  // refetches after data exists, which would flip the whole signed-in dashboard back to
  // <LoadingScreen /> on every revalidation.
  const isLoading = query.isLoading;

  const value: AuthContextValue = {
    user: query.data ? { email: query.data.email, name: query.data.name, picture: query.data.picture } : null,
    csrfToken: query.data?.csrf_token ?? null,
    isLoading,
    isAuthenticated: Boolean(query.data),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
