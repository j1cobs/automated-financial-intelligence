#!/usr/bin/env python3
"""Mint or repair Plaid access tokens without leaving this repo.

Usage:
  python scripts/plaid_link.py create --append
  python scripts/plaid_link.py create --append --owner Jacob --print-token
  python scripts/plaid_link.py repair
  python scripts/plaid_link.py repair --token-suffix 1372c4

`create` opens Plaid Link in your browser and exchanges the resulting public_token for a
new access_token (unless PLAID_BASE_URL is a sandbox endpoint, in which case it mints one
headlessly via /sandbox/public_token/create -- no browser needed).

`repair` re-authenticates an existing, broken Item through Link's *update mode*. The
Item's access_token does not change in update mode, so nothing needs to be written back
to .env or GitHub Secrets -- this only fixes errors like NO_ACCOUNTS / ITEM_LOGIN_REQUIRED
on a token you already have.

Credentials are read the same way the rest of this app reads them: via
core.config.load_settings() (env vars / .streamlit/secrets.toml / .env).
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests

from core.config import ConfigError, load_settings
from ingestion.plaid_link import PlaidLinkClient, classify_item_status

_LINK_PAGE_TEMPLATE = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Plaid Link</title></head>
<body>
<p>Opening Plaid Link...</p>
<script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
<script>
  const handler = Plaid.create({
    token: "__LINK_TOKEN__",
    onSuccess: (public_token, metadata) => {
      fetch("/callback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({public_token: public_token}),
      }).then(() => { document.body.innerText = "Done -- you can close this tab."; });
    },
    onExit: (err, metadata) => {
      fetch("/callback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({error: err ? err.error_code : "user_exited"}),
      }).then(() => { document.body.innerText = "Link closed -- you can close this tab."; });
    },
  });
  handler.open();
</script>
</body>
</html>
"""


class _LinkResult:
    def __init__(self) -> None:
        self.public_token: str | None = None
        self.error: str | None = None


class _LinkCallbackHandler(BaseHTTPRequestHandler):
    # Bound per-instance by run_link_flow() via a subclass created with type().
    link_token: str = ""
    result: _LinkResult
    done_event: threading.Event

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        pass  # keep raw HTTP access logs out of the CLI's own status output

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        body = _LINK_PAGE_TEMPLATE.replace("__LINK_TOKEN__", self.link_token).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if "public_token" in payload:
            self.result.public_token = payload["public_token"]
        else:
            self.result.error = payload.get("error", "Link was closed without completing")

        body = b"<html><body>You can close this tab.</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.done_event.set()


def run_link_flow(link_token: str, timeout_seconds: int = 600) -> str:
    """Serve a minimal Link page on 127.0.0.1, open it in the default browser, and
    block until onSuccess/onExit posts back. Returns the public_token from onSuccess.

    No redirect_uri is set: per Plaid's own docs, redirect_uri is only required for
    mobile clients, so plain http://localhost works here even for OAuth institutions
    on desktop. Nothing in this flow participates in an OAuth redirect.
    """
    result = _LinkResult()
    done_event = threading.Event()

    bound_handler = type(
        "_BoundLinkCallbackHandler",
        (_LinkCallbackHandler,),
        {"link_token": link_token, "result": result, "done_event": done_event},
    )
    server = HTTPServer(("127.0.0.1", 0), bound_handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/"
    print(f"Opening browser at {url} -- complete the bank login there.")
    webbrowser.open(url)

    completed = done_event.wait(timeout=timeout_seconds)
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)

    if not completed:
        raise RuntimeError(f"Timed out after {timeout_seconds}s waiting for Link to complete.")
    if result.error:
        raise RuntimeError(f"Link did not complete: {result.error}")
    assert result.public_token is not None
    return result.public_token


def _is_sandbox(base_url: str) -> bool:
    return "sandbox" in base_url.lower()


def _safe_call(method: Any, *args: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Call a PlaidLinkClient method; on an HTTP error, return Plaid's flat error body
    (see classify_item_status) instead of letting the exception propagate."""
    try:
        return method(*args), None
    except requests.HTTPError as exc:
        try:
            return None, exc.response.json()
        except ValueError:
            return None, {"error_code": "UNKNOWN_ERROR", "error_message": str(exc)}


def _item_status(client: PlaidLinkClient, token: str) -> str:
    item_response, item_error = _safe_call(client.get_item, token)
    if item_error:
        return classify_item_status(item_error, None)
    accounts_response, acc_error = _safe_call(client.get_accounts, token)
    return classify_item_status(item_response or {}, acc_error or accounts_response)


def _load_client(settings: Any) -> PlaidLinkClient:
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise ConfigError("PLAID_CLIENT_ID and PLAID_SECRET are required")
    return PlaidLinkClient(
        client_id=settings.plaid_client_id,
        secret=settings.plaid_secret,
        base_url=settings.plaid_base_url,
    )


def _read_env_lines(env_path: Path) -> list[str]:
    if env_path.exists():
        return env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    return []


def _find_key_line(lines: list[str], key: str) -> int | None:
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(f"{key}="):
            return i
    return None


def _get_csv_value(lines: list[str], key: str) -> list[str]:
    idx = _find_key_line(lines, key)
    if idx is None:
        return []
    _, value = lines[idx].strip().split("=", 1)
    return [item.strip() for item in value.split(",") if item.strip()]


def _set_csv_value(lines: list[str], key: str, values: list[str]) -> list[str]:
    idx = _find_key_line(lines, key)
    new_line = f"{key}={','.join(values)}\n"
    if idx is not None:
        lines[idx] = new_line
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new_line)
    return lines


def append_token_to_env(env_path: Path, token: str, owner: str | None) -> None:
    """Append `token` to PLAID_ACCESS_TOKENS, keeping PLAID_ACCESS_TOKEN_OWNERS the same
    length whenever it's already in use -- pipeline/runner.py raises ConfigError on a
    mismatch, so a write that would create one is refused rather than silently applied."""
    lines = _read_env_lines(env_path)

    tokens = _get_csv_value(lines, "PLAID_ACCESS_TOKENS")
    owners = _get_csv_value(lines, "PLAID_ACCESS_TOKEN_OWNERS")

    if token in tokens:
        print(f"Token already present in {env_path}; leaving PLAID_ACCESS_TOKENS unchanged.")
        return

    tokens.append(token)

    if owners:
        if not owner:
            raise ValueError(
                "PLAID_ACCESS_TOKEN_OWNERS is already set in this file; an owner is required "
                "so the two lists stay the same length."
            )
        owners.append(owner)
    elif owner:
        # Owners aren't tracked yet. A blank placeholder for the pre-existing tokens
        # can't survive a round trip -- _split_csv (core/config.py) drops empty CSV
        # entries, so "," + ",Jacob" would read back as length 1, not 3, recreating
        # the exact mismatch this function exists to prevent. Since a partial owners
        # list isn't representable in this file format, leave owners untracked rather
        # than write state that looks fine now and breaks on the next pipeline run.
        print(
            f"Note: PLAID_ACCESS_TOKEN_OWNERS isn't set yet, so '{owner}' won't be recorded -- "
            "a partial owners list can't be represented in this file format. Add "
            "PLAID_ACCESS_TOKEN_OWNERS manually with an entry for every token if you want to "
            "start tracking owners."
        )

    if owners and len(owners) != len(tokens):
        raise ValueError(
            f"Refusing to write: PLAID_ACCESS_TOKENS would have {len(tokens)} entries but "
            f"PLAID_ACCESS_TOKEN_OWNERS would have {len(owners)}."
        )

    lines = _set_csv_value(lines, "PLAID_ACCESS_TOKENS", tokens)
    if owners:
        lines = _set_csv_value(lines, "PLAID_ACCESS_TOKEN_OWNERS", owners)

    env_path.write_text("".join(lines), encoding="utf-8")


def cmd_create(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = _load_client(settings)

    if _is_sandbox(settings.plaid_base_url):
        print(f"Sandbox base URL detected ({settings.plaid_base_url}); minting headlessly.")
        public_token = client.create_sandbox_public_token(args.institution)
    else:
        print("Production base URL detected; opening Plaid Link in your browser.")
        link_token = client.create_link_token()
        public_token = run_link_flow(link_token)

    access_token = client.exchange_public_token(public_token)
    print(f"Created access_token: ...{access_token[-6:]}")

    if args.print_token:
        print()
        print("Full access token (this is a live credential -- handle it accordingly):")
        print(access_token)

    if args.append:
        env_path = Path(args.env_file)
        owner = args.owner
        existing_owners = _get_csv_value(_read_env_lines(env_path), "PLAID_ACCESS_TOKEN_OWNERS")
        if existing_owners and not owner:
            owner = input(
                f"PLAID_ACCESS_TOKEN_OWNERS already has {len(existing_owners)} entries. "
                "Owner label for this token: "
            ).strip()
        append_token_to_env(env_path, access_token, owner or None)
        print(f"Appended token to {env_path}")
        print()
        print(f"NOTE: {env_path} only affects LOCAL runs. The daily GitHub Actions workflow")
        print("reads the PLAID_ACCESS_TOKENS repo secret, not this file. To use this token")
        print("there, update it manually at: Settings > Secrets and variables > Actions")
        if not args.print_token:
            print("(pass --print-token on this same invocation to also print the full value)")

    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = _load_client(settings)
    tokens = settings.plaid_access_tokens
    owners = settings.plaid_access_token_owners

    if not tokens:
        print("PLAID_ACCESS_TOKENS is empty; nothing to repair.")
        return 1

    print("Configured Plaid Items:\n")
    print(f" {'#':>2}  {'Owner':<10}{'Token':<12}Status")
    for i, token in enumerate(tokens):
        owner = owners[i] if i < len(owners) else ""
        status = _item_status(client, token)
        flag = "" if status.startswith("OK") else "  <- broken"
        print(f" {i + 1:>2}  {owner or '-':<10}...{token[-6:]:<9}{status}{flag}")
    print()

    chosen_token: str | None = None
    if args.token_suffix:
        matches = [t for t in tokens if t.endswith(args.token_suffix)]
        if len(matches) != 1:
            print(f"Expected exactly one token ending in {args.token_suffix!r}, found {len(matches)}.")
            return 1
        chosen_token = matches[0]
    else:
        choice = input(f"Repair which item? [1-{len(tokens)}]: ").strip()
        try:
            chosen_token = tokens[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return 1

    print(f"Opening Link in update mode for token ...{chosen_token[-6:]}")
    link_token = client.create_link_token(access_token=chosen_token)
    run_link_flow(link_token)  # update mode never exchanges -- access_token is unchanged

    print("Link closed. Verifying...")
    accounts_response, acc_error = _safe_call(client.get_accounts, chosen_token)
    if acc_error:
        print(f"Still failing: {classify_item_status(acc_error, None)}")
        return 1

    accounts = (accounts_response or {}).get("accounts", [])
    print(f"\n/accounts/get -> {len(accounts)} account{'s' if len(accounts) != 1 else ''}")
    for account in accounts:
        name = account.get("official_name") or account.get("name", "")
        mask = account.get("mask")
        print(f"  {name}  (....{mask})" if mask else f"  {name}")

    print(f"\nItem ...{chosen_token[-6:]} is healthy.")
    print("Token unchanged -- no GitHub Secret update needed.")
    print("\nNext: python main.py")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Mint a new Plaid Item's access token.")
    create_parser.add_argument(
        "--institution", default="ins_109508", help="Sandbox institution id (sandbox only)."
    )
    create_parser.add_argument("--append", action="store_true", help="Append the token to the .env file.")
    create_parser.add_argument(
        "--owner", default=None, help="Owner label to append to PLAID_ACCESS_TOKEN_OWNERS."
    )
    create_parser.add_argument(
        "--print-token", action="store_true", help="Print the full access token to stdout."
    )
    create_parser.add_argument("--env-file", default=".env", help="Path to .env file to update.")

    repair_parser = subparsers.add_parser(
        "repair", help="Re-authenticate a broken Plaid Item via Link update mode."
    )
    repair_parser.add_argument(
        "--token-suffix", default=None, help="Last 6+ characters of the token to repair."
    )

    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.command == "create":
        return cmd_create(args)
    if args.command == "repair":
        return cmd_repair(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
