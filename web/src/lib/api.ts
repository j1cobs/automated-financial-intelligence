/**
 * Typed fetch wrapper for every call into the FastAPI backend. Used inside
 * every TanStack Query `queryFn`/`mutationFn` — never call `fetch` directly
 * elsewhere, so the cross-origin cookie/CSRF handling stays in one place.
 *
 * - `credentials: 'include'` on every request: the API's session cookie is
 *   cross-origin by design (web and api are hosted on different platform
 *   subdomains), so without this the cookie is neither sent nor stored.
 * - `X-CSRF-Token` header attached on every non-GET request, sourced from
 *   `authStore` (populated from the `csrf_token` field of the most recent
 *   `GET /auth/me` response). The API rejects writes without a matching
 *   token (double-submit CSRF check, see api/deps.py::require_csrf).
 * - A 401 response throws `UnauthorizedError` AND fires the `authStore`
 *   unauthorized-listener callback, so `AuthProvider` can react globally
 *   (any 401 after a prior successful sign-in means "session expired").
 */

import { getCsrfToken, notifyUnauthorized } from './authStore';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

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
 * Fetch a path relative to `VITE_API_URL`. Pass a JSON-serializable value as
 * `body`; it's serialized and given a `Content-Type: application/json`
 * header automatically. GET requests should omit `body`.
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
