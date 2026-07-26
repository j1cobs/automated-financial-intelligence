from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ingestion.plaid_link import PlaidLinkClient, classify_item_status
from scripts.plaid_link import _get_csv_value, _read_env_lines, append_token_to_env


class LinkTokenPayloadTests(unittest.TestCase):
    """The create/update split in PlaidLinkClient.create_link_token is the part most
    likely to silently misfire against Plaid: sending `products` in update mode is
    rejected outright, and forgetting `access_token` in update mode creates a brand new
    Item instead of repairing the existing one."""

    def setUp(self) -> None:
        self.client = PlaidLinkClient("cid", "secret", "https://production.plaid.com")

    def test_create_mode_sends_products_no_access_token(self) -> None:
        with patch.object(self.client, "_post", return_value={"link_token": "tok"}) as mock_post:
            self.client.create_link_token()
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload["products"], ["transactions"])
        self.assertNotIn("access_token", payload)
        self.assertNotIn("update", payload)

    def test_update_mode_sends_access_token_no_products(self) -> None:
        with patch.object(self.client, "_post", return_value={"link_token": "tok"}) as mock_post:
            self.client.create_link_token(access_token="existing-token")
        payload = mock_post.call_args[0][1]
        self.assertNotIn("products", payload)
        self.assertEqual(payload["access_token"], "existing-token")
        self.assertEqual(payload["update"], {"account_selection_enabled": True})

    def test_create_link_token_returns_link_token_field(self) -> None:
        with patch.object(self.client, "_post", return_value={"link_token": "link-abc"}):
            result = self.client.create_link_token()
        self.assertEqual(result, "link-abc")

    def test_exchange_public_token_returns_access_token_field(self) -> None:
        with patch.object(self.client, "_post", return_value={"access_token": "access-xyz"}) as mock_post:
            result = self.client.exchange_public_token("public-abc")
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload["public_token"], "public-abc")
        self.assertEqual(result, "access-xyz")

    def test_create_sandbox_public_token_hits_sandbox_endpoint(self) -> None:
        with patch.object(self.client, "_post", return_value={"public_token": "public-sandbox"}) as mock_post:
            result = self.client.create_sandbox_public_token("ins_109508")
        endpoint = mock_post.call_args[0][0]
        payload = mock_post.call_args[0][1]
        self.assertEqual(endpoint, "sandbox/public_token/create")
        self.assertEqual(payload["institution_id"], "ins_109508")
        self.assertEqual(payload["initial_products"], ["transactions"])
        self.assertEqual(result, "public-sandbox")


class ItemStatusTests(unittest.TestCase):
    """classify_item_status reads Plaid's actual error shape: a flat JSON body with
    error_code at the top level, not nested under an "error" key -- the exact shape
    seen in the NO_ACCOUNTS failure that prompted this tool."""

    def test_no_accounts_error_from_item_response(self) -> None:
        error_body = {
            "display_message": "No valid accounts were found at the financial institution.",
            "documentation_url": "https://plaid.com/docs/errors/item/#no_accounts",
            "error_code": "NO_ACCOUNTS",
            "error_message": "no valid accounts were found for this item",
            "error_type": "ITEM_ERROR",
            "request_id": "03c6688b0ee2d66",
            "suggested_action": None,
        }
        self.assertEqual(classify_item_status(error_body, None), "NO_ACCOUNTS")

    def test_item_login_required_error(self) -> None:
        error_body = {"error_code": "ITEM_LOGIN_REQUIRED", "error_type": "ITEM_ERROR"}
        self.assertEqual(classify_item_status(error_body, None), "ITEM_LOGIN_REQUIRED")

    def test_error_surfaced_from_accounts_response_when_item_ok(self) -> None:
        item_response = {"item": {"item_id": "item-1"}}
        accounts_error = {"error_code": "PRODUCT_NOT_READY"}
        self.assertEqual(classify_item_status(item_response, accounts_error), "PRODUCT_NOT_READY")

    def test_healthy_item_reports_account_count_plural(self) -> None:
        item_response = {"item": {"item_id": "item-1"}}
        accounts_response = {"accounts": [{"account_id": "a"}, {"account_id": "b"}]}
        self.assertEqual(classify_item_status(item_response, accounts_response), "OK (2 accounts)")

    def test_healthy_item_reports_account_count_singular(self) -> None:
        item_response = {"item": {"item_id": "item-1"}}
        accounts_response = {"accounts": [{"account_id": "a"}]}
        self.assertEqual(classify_item_status(item_response, accounts_response), "OK (1 account)")

    def test_healthy_item_with_zero_accounts_still_reports_ok(self) -> None:
        # Not an error response -- just an Item with no accounts array populated yet.
        item_response = {"item": {"item_id": "item-1"}}
        accounts_response = {"accounts": []}
        self.assertEqual(classify_item_status(item_response, accounts_response), "OK (0 accounts)")


class EnvWriterTests(unittest.TestCase):
    """append_token_to_env must never leave PLAID_ACCESS_TOKENS and
    PLAID_ACCESS_TOKEN_OWNERS at different lengths -- pipeline/runner.py raises
    ConfigError on exactly that mismatch, so a write that would create one must be
    refused rather than silently applied. Every case here writes to a tmp_path file,
    never the real .env."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.env_path = Path(self._tmpdir.name) / "test.env"

    def test_append_to_fresh_file_with_no_owner_leaves_owners_empty(self) -> None:
        append_token_to_env(self.env_path, "tokA", None)
        lines = _read_env_lines(self.env_path)
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKENS"), ["tokA"])
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKEN_OWNERS"), [])

    def test_append_with_existing_owners_stays_in_lockstep(self) -> None:
        self.env_path.write_text("PLAID_ACCESS_TOKENS=tokA,tokB\nPLAID_ACCESS_TOKEN_OWNERS=Alex,Sam\n")
        append_token_to_env(self.env_path, "tokC", "Jacob")
        lines = _read_env_lines(self.env_path)
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKENS"), ["tokA", "tokB", "tokC"])
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKEN_OWNERS"), ["Alex", "Sam", "Jacob"])

    def test_refuses_write_when_owners_set_but_no_owner_given(self) -> None:
        self.env_path.write_text("PLAID_ACCESS_TOKENS=tokA\nPLAID_ACCESS_TOKEN_OWNERS=Alex\n")
        with self.assertRaises(ValueError):
            append_token_to_env(self.env_path, "tokB", None)
        # The file must be left untouched by the refused write.
        lines = _read_env_lines(self.env_path)
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKENS"), ["tokA"])

    def test_owner_given_but_owners_not_yet_tracked_is_not_written(self) -> None:
        # A blank CSV placeholder for the pre-existing tokens can't round-trip through
        # core/config.py's _split_csv (it drops empty entries), so starting a partial
        # owners list here would silently recreate the length-mismatch ConfigError this
        # function exists to prevent. The owner is dropped, not written as "" entries.
        self.env_path.write_text("PLAID_ACCESS_TOKENS=tokA,tokB\n")
        append_token_to_env(self.env_path, "tokC", "Jacob")
        lines = _read_env_lines(self.env_path)
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKENS"), ["tokA", "tokB", "tokC"])
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKEN_OWNERS"), [])

    def test_dedupes_already_present_token(self) -> None:
        self.env_path.write_text("PLAID_ACCESS_TOKENS=tokA\n")
        append_token_to_env(self.env_path, "tokA", None)
        lines = _read_env_lines(self.env_path)
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKENS"), ["tokA"])

    def test_preserves_comments_and_unrelated_keys(self) -> None:
        self.env_path.write_text("# a comment\nDATABASE_URL=postgres://x\nPLAID_ACCESS_TOKENS=tokA\n")
        append_token_to_env(self.env_path, "tokB", None)
        content = self.env_path.read_text()
        self.assertIn("# a comment", content)
        self.assertIn("DATABASE_URL=postgres://x", content)

    def test_creates_file_when_missing(self) -> None:
        self.assertFalse(self.env_path.exists())
        append_token_to_env(self.env_path, "tokA", None)
        self.assertTrue(self.env_path.exists())
        lines = _read_env_lines(self.env_path)
        self.assertEqual(_get_csv_value(lines, "PLAID_ACCESS_TOKENS"), ["tokA"])


if __name__ == "__main__":
    unittest.main()
