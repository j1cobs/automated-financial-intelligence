"""Check whether /transactions/recurring/get is entitled on this Plaid account.

Recurring Transactions is an **add-on** to the Transactions product. Plaid's
docs say it is available in the US, Canada and the UK and is supported by the
same institutions that support Transactions, and that it works with existing
access tokens (no re-link, no update mode) -- but whether it is switched on for
a given Plaid account is a dashboard setting this code cannot see.

So: run this once. If streams come back, Phase 30 uses the Plaid path. If it
reports the product is not enabled, `analytics.recurring.derive_streams` covers
the same ground from our own history, producing rows of an identical shape.

This script only reads. It never writes to the database.

Logging is scrubbed to the same standard as `PlaidIngestor._post`: status code
and Plaid's error_type/error_code only, never the raw response body and never
an account mask. The daily pipeline's stdout becomes the GitHub Actions run
log, which anyone with repo read access can see.

Usage:
    python scripts/probe_plaid_recurring.py            # probes the first token
    python scripts/probe_plaid_recurring.py --all      # probes every token
"""

from __future__ import annotations

import argparse
import logging

import requests

from core.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

#: Plaid returns this when the product is not enabled for the account.
_NOT_ENTITLED_CODES = {
    "PRODUCTS_NOT_SUPPORTED",
    "PRODUCT_NOT_READY",
    "PRODUCT_NOT_ENABLED",
    "INVALID_PRODUCT",
    "ADDITIONAL_CONSENT_REQUIRED",
}


def probe(base_url: str, client_id: str, secret: str, access_token: str, label: str) -> bool:
    """Probe one token. Returns whether usable stream data came back."""
    try:
        response = requests.post(
            f"{base_url}/transactions/recurring/get",
            json={"client_id": client_id, "secret": secret, "access_token": access_token},
            timeout=30,
        )
    except requests.RequestException as error:
        LOGGER.error("[%s] request failed: %s", label, type(error).__name__)
        return False

    if response.ok:
        body = response.json()
        inflow = len(body.get("inflow_streams", []))
        outflow = len(body.get("outflow_streams", []))
        LOGGER.info(
            "[%s] ENTITLED -- %d inflow / %d outflow stream(s) returned.",
            label,
            inflow,
            outflow,
        )
        if inflow + outflow == 0:
            LOGGER.warning(
                "[%s] The endpoint works but returned nothing. Plaid wants ~180 days "
                "of history for good results; this Item may not have enough yet.",
                label,
            )
        return True

    error_type = error_code = None
    try:
        body = response.json()
        error_type = body.get("error_type")
        error_code = body.get("error_code")
    except ValueError:
        pass

    # Never log response.text -- it can carry account- and transaction-identifying detail.
    LOGGER.error(
        "[%s] NOT usable -- status=%s error_type=%s error_code=%s",
        label,
        response.status_code,
        error_type,
        error_code,
    )
    if error_code in _NOT_ENTITLED_CODES:
        LOGGER.error(
            "[%s] That code means the add-on is not enabled for this Plaid account. "
            "Request Recurring Transactions in the Plaid dashboard, or leave Phase 30 "
            "on the local-derivation fallback.",
            label,
        )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Probe every configured token, not just the first")
    args = parser.parse_args()

    settings = load_settings()
    tokens = [t for t in (settings.plaid_access_tokens or []) if t]
    if not tokens:
        LOGGER.error("No PLAID_ACCESS_TOKENS configured; nothing to probe.")
        return 1
    if not settings.plaid_client_id or not settings.plaid_secret:
        LOGGER.error("PLAID_CLIENT_ID / PLAID_SECRET are not set.")
        return 1

    selected = tokens if args.all else tokens[:1]
    base_url = settings.plaid_base_url.rstrip("/")

    results = []
    for index, token in enumerate(selected, start=1):
        # Tokens are secrets: identify them by position, never by value or suffix.
        results.append(
            probe(base_url, settings.plaid_client_id, settings.plaid_secret, token, f"token {index}")
        )

    if any(results):
        LOGGER.info("Recurring Transactions is usable. Phase 30 can use the Plaid path.")
        return 0

    LOGGER.warning(
        "No token returned usable stream data. Phase 30 falls back to "
        "analytics.recurring.derive_streams, which produces the same table shape."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
