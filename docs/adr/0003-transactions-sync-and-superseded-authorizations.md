# ADR 0003: Transactions sync and superseded authorizations

## Status

Accepted (2026-08-25). Complements ADR 0002 (transaction identity); live production phase.

## Context

A hotel stay at Le Germain produced **five stored transaction rows** where the real charge was **one**. The account holder booked the room, put down a deposit to secure the stay, and ate at the restaurant; the card issuer authorized each separately. These four authorizations were then settled into a single `-$723.01` charge.

**Root cause.** The production ingestion path (`ingestion/plaid_ingestor.py:fetch_transactions`) uses Plaid's `/transactions/get` endpoint. In Plaid's model, when a pending authorization posts, it becomes a **brand-new transaction with a new `transaction_id`**. The pending one simply **stops appearing** in the response. There is no removal signal.

`build_transaction_hash` (ADR 0002) keys on `transaction_id`, so the settled charge lands as a new row. The four superseded authorizations persist in the database forever — each with a distinct amount, so `reconcile_transactions`'s natural-key guard (which uses Plaid's per-natural-key counts) deliberately skips them, fearing it is real history aged out of Plaid's rolling window.

**The problem is structural.** Without an authoritative removal signal, no heuristic can tell a superseded authorization from a legitimate old transaction Plaid is no longer syncing. The root cause is not the hash formula or duplicate-detection logic — it is that the endpoint itself provides no information to distinguish these cases.

## Decision

**Migrate the live ingestion path to `/transactions/sync`, whose `removed` array reports superseded and reversed transactions explicitly.**

This endpoint replaces the append-only `/transactions/get`. For each Plaid Item (access token), the caller maintains a cursor stored in the new `plaid_sync_state` table (keyed by `sha256(access_token)` fingerprint — never the raw token). Sync returns three arrays: `added` (new transactions since the cursor), `modified` (transactions that changed), and `removed` (transaction_ids no longer present). The removed array is authoritative.

**Confirmed by live probe (2026-08-25, all three institutions):** `removed_ids` must be the union of Plaid's explicit `removed` array *and* every non-null `pending_transaction_id` carried by an `added`/`modified` row. On a cold-start sync (`cursor=null`), the `removed` array is empty (no prior baseline to remove from), but the settled Le Germain charge came back carrying `pending_transaction_id` pointing at a stale row already stored in the database. That pointer is the only lineage evidence a cold start gives. Going forward on incremental syncs, the same merge normally surfaces through `removed` directly; folding `pending_transaction_id` in as well is a no-cost superset, not a replacement. This mechanism justifies deletion on exact Plaid lineage.

**`reconcile_transactions` is kept but structurally gated.** It still covers a case sync's `removed` does not handle: after an Item re-link, full history re-downloads under brand-new transaction_ids for accounts that already have stored rows. But reconcile must never run against a delta — if Plaid modifies one row out of four genuine IKEA-style repeats, the delta carries one row for that natural key, the database holds four, and reconcile would compute excess=3 and delete three real transactions Plaid never said anything about (the IKEA-delta hazard, documented in code). This is now prevented structurally: `reconcile_transactions` requires a keyword-only `full_refresh: bool` parameter and raises `ValueError` if False. The caller (`pipeline/runner.py`) only passes True when `SyncResult.full_refresh` is True — which happens only when every configured Plaid token started its sync from a null cursor.

**Deletion (not flagging) is justified for `removed`/`pending_transaction_id`:** `removed` and `pending_transaction_id` are Plaid's own authoritative statements that a transaction_id no longer exists, not a heuristic guess. `is_duplicate` (ADR 0002) stays reserved for cases with no such authoritative signal — user judgement on ambiguous cases.

**`fetch_transactions` is kept as a rollback fallback, not deleted.** The old `/transactions/get` path remains in `PlaidIngestor` for emergency fallback only. Once sync runs cleanly in production for ~2 weeks (verifying it handles the full transaction history correctly and that removal actually resolves the authorization issue), the old method should be deleted in a follow-up cleanup phase.

## Consequences

- **Cursor state.** `plaid_sync_state` (migration 018) stores one row per Item, keyed by `sha256(access_token)` fingerprint. The raw token is never stored. Cursors advance only after every write (upsert, delete, reconcile if applicable) has committed; advancing earlier would mean a crash mid-write loses that delta permanently.
- **Pending-authorization lineage.** `transactions.pending` (boolean, nullable) and `transactions.pending_transaction_id` (text) are new (migration 019). `pending` is nullable on purpose: NULL means "ingested before this phase, status unknown" — which is exactly the state of the four pre-existing Germain rows and must not be confused with FALSE. `pending` and `pending_transaction_id` round-trip through the upsert but are not yet surfaced in the API or dashboard; a future decision will determine whether to show pending authorizations in the ledger UI.
- **The four pre-existing Germain rows.** They predate any sync baseline, so no delta will ever carry a `removed` signal for them. The user flags them manually via the existing `is_duplicate` checkbox in the dashboard. This is expected, not a bug — it is real data that has accumulated before the fix, and no backward-pass cleanup was built.
- **Incremental vs. full-refresh deltas.** After the first sync run (always a full refresh), most runs are incremental — `pipeline/runner.py` simply does not call `reconcile_transactions` at all in that case (`if result.full_refresh: ...`). The `ValueError` guard inside `reconcile_transactions` is a safety net against a future caller forgetting this check, not a path exercised in normal operation. Reconciliation runs only when `full_refresh=True`, which is rare, and the run's `full_refresh`/`removed_count` are both logged to `pipeline_runs` for visibility.

## Alternatives considered

- **Keep `/transactions/get` and infer removal from absence:** Rejected — the Germain case proves absence cannot be distinguished from real history aging out of Plaid's window.
- **Flag (not delete) everything in `removed_ids`:** Rejected — `removed` is authoritative. Flagging is appropriate for ambiguous cases (ADR 0002's mechanism C); deletions are appropriate when Plaid explicitly says a transaction_id is gone.
- **Delete `reconcile_transactions` entirely:** Rejected — it is still the only mechanism that catches re-issued transaction_ids after an Item re-link, and its safety properties (reject deltas, keep zero-count keys) are sound when properly gated. The gate is new; the logic is correct.
