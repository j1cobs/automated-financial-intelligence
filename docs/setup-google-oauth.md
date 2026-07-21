# Setting up Google OAuth

The dashboard uses Google sign-in (PKCE) to authenticate. You need your own OAuth client; there's no shared one.

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Go to **APIs & Services > OAuth consent screen**, choose **External**, and add your own email (and anyone else you want signed in) as a test user.
3. Go to **Credentials > Create credentials > OAuth client ID**, and choose **Web application**.
4. Under **Authorized redirect URIs**, add `http://localhost:8501/` for local development. It has to match `GOOGLE_OAUTH_REDIRECT_URI` exactly, trailing slash included. For a public deployment, add a second URI with your deployed HTTPS URL and point `GOOGLE_OAUTH_REDIRECT_URI` at that instead. Mobile sign-in depends on this being HTTPS.
5. Copy the client ID and secret into `.env` as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.
6. Set `GOOGLE_ALLOWED_EMAILS` to a comma-separated list of the addresses allowed to sign in. This list is checked in code after the OAuth handshake completes. An empty list means nobody gets in.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `redirect_uri_mismatch` | The URI Google receives doesn't exactly match one registered in the console. Check for a missing trailing slash or `http` vs `https`. |
| "App not verified" screen | Your Google Cloud project is still in testing mode. Add your email as a test user under the OAuth consent screen, or submit the app for verification if you need broader access. |
| "Session expired" right after signing in | Streamlit restarted (a redeploy, a code change under `--server.runOnSave`) between the redirect out and the redirect back. Sign in again. Sessions are capped at 4 hours by design, so this isn't a bug to chase. |
