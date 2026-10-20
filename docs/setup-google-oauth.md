# Setting up Google OAuth

The dashboard uses Google sign-in (PKCE), handled by the API (`api/routers/auth.py`), to authenticate. You need your own OAuth client; there's no shared one.

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Go to **APIs & Services > OAuth consent screen**, choose **External**, and add your own email (and anyone else you want signed in) as a test user.
3. Go to **Credentials > Create credentials > OAuth client ID**, and choose **Web application**.
4. Under **Authorized redirect URIs**, add the API's callback. For local development that is `http://localhost:8000/auth/google/callback` (uvicorn's default port). For a public deployment, add `https://<your-app>.vercel.app/api/auth/google/callback`: the browser-facing URL goes through the Vercel `/api/*` rewrite to the API's `/auth/google/callback`, which is what keeps the session cookie first-party. Whichever you use has to match `GOOGLE_OAUTH_REDIRECT_URI` exactly; point that variable at the one for the environment you're running. Mobile sign-in depends on the deployed URI being HTTPS. See [deployment.md](deployment.md) for the rest of the deployed setup.
5. Copy the client ID and secret into `.env` as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.
6. Set `GOOGLE_ALLOWED_EMAILS` to a comma-separated list of the addresses allowed to sign in. This list is checked in code after the OAuth handshake completes. An empty list means nobody gets in.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `redirect_uri_mismatch` | The URI Google receives doesn't exactly match one registered in the console. Check for a typo in the path, a stray trailing slash, or `http` vs `https`. |
| "App not verified" screen | Your Google Cloud project is still in testing mode. Add your email as a test user under the OAuth consent screen, or submit the app for verification if you need broader access. |
| Bounced back to the sign-in page with an error right after consenting | The callback failed: the pending sign-in state expired (it lives 10 minutes) or was lost, the address isn't in `GOOGLE_ALLOWED_EMAILS`, or `JWT_SECRET` or the client credentials are unset on the API. Sign in again; check the API logs if it repeats. Sessions last 1 hour by design, so being signed out later isn't a bug to chase. |
| Sign-in loops, or `/auth/me` returns 401 after a successful Google sign-in | The session cookie never became first-party. On a deployment, `GOOGLE_OAUTH_REDIRECT_URI` must be the Vercel `/api/auth/google/callback` URL, not the Render one. |
