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
      // `resetQueries` (not `setQueryData(undefined)`, which is a no-op —
      // an `undefined` update is ignored by TanStack Query) both purges the
      // cached user, so `isAuthenticated` doesn't keep stale data around,
      // and refetches the active query in one step.
      queryClient.resetQueries({ queryKey: AUTH_ME_QUERY_KEY });
    });
  }, [queryClient]);

  useEffect(() => {
    if (query.data) {
      setCsrfToken(query.data.csrf_token);
    } else if (query.isError) {
      setCsrfToken(null);
    }
  }, [query.data, query.isError]);

  // `isPending` covers the initial "no data, no error yet" state; `isFetching`
  // stays true across every cold-start retry attempt. Together they cover
  // "still trying" and go false only once the query settles (success, or a
  // 401 that's exhausted its retries — see `shouldRetry` in queryClient.ts).
  const isLoading = query.isPending || query.isFetching;

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
