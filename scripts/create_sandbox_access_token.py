#!/usr/bin/env python3
"""Create a Plaid sandbox access token and optionally add it to .env.

Usage:
  python scripts/create_sandbox_access_token.py --append
  python scripts/create_sandbox_access_token.py --institution ins_109508 --append

This script reads PLAID_CLIENT_ID and PLAID_SECRET from the environment.
It posts to the sandbox `/sandbox/public_token/create` endpoint to get a public_token,
then exchanges it for an access_token at `/item/public_token/exchange`.

If `--append` is provided, the script will update or add the `PLAID_ACCESS_TOKENS`
entry in the specified `.env` file (default: .env) by appending the new token
if it's not already present.
"""

from __future__ import annotations

import argparse
from http import client
import json
import os
import sys
from typing import List

import requests

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = os.environ.get("PLAID_BASE_URL", "https://sandbox.plaid.com")
DEFAULT_INSTITUTION = "ins_109508"
DEFAULT_PRODUCTS = ["transactions"]


def create_public_token(client_id: str, secret: str, institution_id: str, products: List[str], base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/sandbox/public_token/create"
    payload = {
        "client_id": client_id,
        "secret": secret,
        "institution_id": institution_id,
        "initial_products": products,
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["public_token"]


def exchange_public_token(client_id: str, secret: str, public_token: str, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/item/public_token/exchange"
    payload = {"client_id": client_id, "secret": secret, "public_token": public_token}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


def update_env_file(env_path: str, token: str) -> None:
    # Read existing file (if any)
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

    key = "PLAID_ACCESS_TOKENS"
    token_list = []
    found = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(f"{key}="):
            found = True
            _, val = line.split("=", 1)
            token_list = [t.strip() for t in val.split(",") if t.strip()]
            if token not in token_list:
                token_list.append(token)
            # replace the line
            lines[i] = f"{key}={','.join(token_list)}\n"
            break

    if not found:
        # append new line
        lines.append(f"{key}={token}\n")

    with open(env_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--institution", default=DEFAULT_INSTITUTION)
    parser.add_argument("--products", default=",".join(DEFAULT_PRODUCTS))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--append", action="store_true", help="Append the token to the .env file")
    parser.add_argument("--env-file", default=".env", help="Path to .env file to update")
    args = parser.parse_args()

    client_id = os.environ.get("PLAID_CLIENT_ID")
    secret = os.environ.get("PLAID_SECRET")

    if not client_id or not secret:
        print("ERROR: PLAID_CLIENT_ID and PLAID_SECRET must be set in the environment.")
        return 2

    try:
        public_token = create_public_token(client_id, secret, args.institution, [p.strip() for p in args.products.split(",") if p.strip()], args.base_url)
        access_token = exchange_public_token(client_id, secret, public_token, args.base_url)
    except requests.RequestException as exc:
        print("ERROR: Plaid API request failed:", exc)
        return 3

    print("Created access_token:", access_token)
    print()
    print("Add this to your .env file (or use --append):")
    print(f"PLAID_ACCESS_TOKENS={access_token}")

    if args.append:
        update_env_file(args.env_file, access_token)
        print(f"Appended token to {args.env_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
