/**
 * Tiny module-level store bridging the auth state (`useAuth`, backed by the
 * `GET /auth/me` TanStack Query) and the fetch wrapper (`lib/api.ts`).
 *
 * Why not just read from React context inside `api.ts`? `queryFn`/`mutationFn`
 * callbacks run outside the component tree (TanStack Query owns their
 * lifecycle), so they cannot call `useContext`. The CSRF token is written here
 * once per successful `/auth/me` response and read back on every non-GET
 * request. Never persisted to storage (localStorage/sessionStorage) — only
 * held in memory, per the plan's requirement.
 */

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

/**
 * Fired whenever any API call gets a 401 back. `AuthProvider` subscribes to
 * this once at startup so a 401 on *any* endpoint (not just `/auth/me`) can
 * invalidate the auth query and fall back to the sign-in page — see the
 * "session expired" requirement in the R3 plan.
 */
type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export function notifyUnauthorized(): void {
  for (const listener of unauthorizedListeners) listener();
}
