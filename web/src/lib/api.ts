/**
 * Typed fetch wrapper for every call into the FastAPI backend. Used inside
 * every TanStack Query `queryFn`/`mutationFn` — never call `fetch` directly
 * elsewhere, so the cookie/CSRF handling stays in one place.
 *
 * - Requests go to the relative `/api` prefix, never an absolute cross-origin
 *   URL. In production, `web/vercel.json` rewrites `/api/*` to the Render API
 *   server-to-server; in dev, `web/vite.config.ts`'s `server.proxy` does the
 *   same against localhost. Either way the *browser* only ever talks to one
 *   origin (Vercel's, or Vite's own dev server), so the session cookie the
 *   API sets is first-party, not third-party — this is what fixes iOS
 *   Safari's ITP blocking the cookie and looping the sign-in flow.
 * - `credentials: 'include'` is kept even though the request is same-origin:
 *   harmless there, and still required for the pre-proxy direct-Render calls
 *   used in local `curl`/manual testing.
 * - `X-CSRF-Token` header attached on every non-GET request, sourced from
 *   `authStore` (populated from the `csrf_token` field of the most recent
 *   `GET /auth/me` response). The API rejects writes without a matching
 *   token (double-submit CSRF check, see api/deps.py::require_csrf) — kept
 *   as defense-in-depth even though the cookie is now first-party.
 * - A 401 response throws `UnauthorizedError` AND fires the `authStore`
 *   unauthorized-listener callback, so `AuthProvider` can react globally
 *   (any 401 after a prior successful sign-in means "session expired").
 */

import { getCsrfToken, notifyUnauthorized } from './authStore';

const API_URL = '/api';

export class UnauthorizedError extends Error {
  constructor() {
    super('Not authenticated');
    this.name = 'UnauthorizedError';
  }
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

/**
 * Fetch a path relative to the `/api` proxy prefix. Pass a JSON-serializable
 * value as `body`; it's serialized and given a `Content-Type:
 * application/json` header automatically. GET requests should omit `body`.
 */
export async function apiFetch<T = unknown>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { body, headers, method, ...rest } = options;
  const resolvedMethod = method ?? (body !== undefined ? 'POST' : 'GET');

  const requestHeaders = new Headers(headers);
  if (body !== undefined) {
    requestHeaders.set('Content-Type', 'application/json');
  }
  if (resolvedMethod !== 'GET' && resolvedMethod !== 'HEAD') {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      requestHeaders.set('X-CSRF-Token', csrfToken);
    }
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    method: resolvedMethod,
    headers: requestHeaders,
    credentials: 'include',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401) {
    notifyUnauthorized();
    throw new UnauthorizedError();
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data?.detail) message = data.detail;
    } catch {
      // Response body wasn't JSON (or was empty) — keep the generic message.
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export { API_URL };
