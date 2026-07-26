from __future__ import annotations

import logging
import uuid
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


class PlaidLinkClient:
    """Plaid Link token lifecycle: create/update link_token, exchange public_token,
    and read back Item/account state. Separate from PlaidIngestor, whose job is
    fetching transactions for an already-exchanged access_token."""

    def __init__(
        self,
        client_id: str,
        secret: str,
        base_url: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.client_id = client_id
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/{endpoint}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            LOGGER.error("Plaid error response: %s", response.text)
        response.raise_for_status()
        return response.json()

    def create_link_token(
        self,
        *,
        access_token: str | None = None,
        client_name: str = "Automated Financial Intelligence",
        country_codes: list[str] | None = None,
        language: str = "en",
    ) -> str:
        """Create a link_token. Passing access_token switches this into *update mode*:
        no `products` may be sent (Plaid rejects that combination), the existing Item's
        access_token is reused as-is, and account_selection_enabled lets the user
        re-pick accounts on an Item that returned NO_ACCOUNTS."""
        payload: dict[str, Any] = {
            "client_id": self.client_id,
            "secret": self.secret,
            "client_name": client_name,
            "country_codes": country_codes or ["US"],
            "language": language,
            "user": {"client_user_id": str(uuid.uuid4())},
        }
        if access_token:
            payload["access_token"] = access_token
            payload["update"] = {"account_selection_enabled": True}
        else:
            payload["products"] = ["transactions"]

        data = self._post("link/token/create", payload)
        return data["link_token"]

    def exchange_public_token(self, public_token: str) -> str:
        data = self._post(
            "item/public_token/exchange",
            {
                "client_id": self.client_id,
                "secret": self.secret,
                "public_token": public_token,
            },
        )
        return data["access_token"]

    def create_sandbox_public_token(self, institution_id: str, products: list[str] | None = None) -> str:
        """Sandbox-only shortcut: mints a public_token without any browser/Link step."""
        data = self._post(
            "sandbox/public_token/create",
            {
                "client_id": self.client_id,
                "secret": self.secret,
                "institution_id": institution_id,
                "initial_products": products or ["transactions"],
            },
        )
        return data["public_token"]

    def get_item(self, access_token: str) -> dict[str, Any]:
        return self._post(
            "item/get",
            {"client_id": self.client_id, "secret": self.secret, "access_token": access_token},
        )

    def get_accounts(self, access_token: str) -> dict[str, Any]:
        return self._post(
            "accounts/get",
            {"client_id": self.client_id, "secret": self.secret, "access_token": access_token},
        )


def classify_item_status(item_response: dict[str, Any], accounts_response: dict[str, Any] | None) -> str:
    """Summarize an Item's health from /item/get (+ /accounts/get if that call succeeded).

    Plaid error bodies are flat JSON with `error_code` at the top level (not nested under
    an "error" key) -- see the NO_ACCOUNTS payload this tool exists to diagnose:
    {"error_code": "NO_ACCOUNTS", "error_type": "ITEM_ERROR", ...}. Callers pass that raw
    error body straight through as item_response/accounts_response when a call failed.
    accounts_response is None when accounts/get was never reached (item_response already
    carries an error).
    """
    for response in (item_response, accounts_response):
        if response and "error_code" in response:
            return str(response["error_code"])

    accounts = (accounts_response or {}).get("accounts", [])
    return f"OK ({len(accounts)} account{'s' if len(accounts) != 1 else ''})"
