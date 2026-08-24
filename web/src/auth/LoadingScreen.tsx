/**
 * Shown while `GET /auth/me` is loading, including any cold-start retry —
 * the Render free tier can take 30s+ to wake from idle, so this must read as
 * "the server is starting up," not a blank screen or an error.
 */
export function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-page px-4">
      <div className="flex flex-col items-center gap-3 text-center">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-strong border-t-ink"
          role="status"
          aria-label="Loading"
        />
        <p className="text-sm text-ink-muted">Waking up the server&hellip; this can take up to a minute.</p>
      </div>
    </div>
  );
}
