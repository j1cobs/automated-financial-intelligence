import { API_URL } from '../lib/api';

/**
 * A real navigation, not a fetch — the browser needs to follow Google's
 * OAuth redirect chain and land back on the API's callback, which then
 * redirects to this app with the session cookie already set. The `/api`
 * prefix is same-origin (proxied to the API — see `lib/api.ts`'s top
 * comment), which is what makes the resulting cookie first-party and
 * avoids iOS Safari's ITP blocking it.
 */
const GOOGLE_START_URL = `${API_URL}/auth/google/start`;

export function SignIn() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-page px-4">
      <div className="w-full max-w-sm rounded-xl border border-hairline bg-surface-1 p-8 text-center shadow-sm">
        <h1 className="mb-2 text-xl font-semibold text-ink">Automated Financial Intelligence</h1>
        <p className="mb-6 text-sm text-ink-muted">Sign in with an allowlisted Google account to continue.</p>
        <a
          href={GOOGLE_START_URL}
          className="inline-flex w-full items-center justify-center rounded-md bg-ink px-4 py-2.5 text-sm font-medium text-on-emphasis transition hover:opacity-90"
        >
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
