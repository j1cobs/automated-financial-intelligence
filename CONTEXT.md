# Domain glossary

- **Account** — a real account at a financial institution (a chequing account, a credit card, an
  investment account). Durable across Plaid Item re-links; the *same* Account should always be
  represented by exactly one row.

- **Account key** — the Plaid-issued, Item-scoped identifier used as the `accounts.account_key`
  primary key. *Not* durable: a Plaid Item re-link (e.g. after rotating access tokens) issues a
  new one for the same Account.

- **Identity key** — the heuristic tuple `(official_name, account_subtype, account_type, mask)`
  used to recognise that two `accounts` rows with different account keys represent the same
  Account. Deliberately excludes owner (see Owner, below).

- **Account fork** — the failure state where one Account ends up represented by two `accounts`
  rows with split transaction history, because the identity key failed to recognise them as the
  same Account across a re-link.

- **Canonical row / Orphan row** — within an Account fork, the *canonical row* is the account key
  Plaid is still actively syncing; the *orphan row* is the account key Plaid no longer issues.
  Merging always reassigns history onto the canonical row and deletes the orphan.

- **Owner** — a label recording which connection (Plaid access token) revealed an Account, not
  legal or financial ownership. A jointly-held account is currently represented with a single
  owner label, whichever connection happened to reveal it.

- **Mask** — the last four characters of an account number, as reported by Plaid. Unique only
  *within* an identity key, not globally — the same mask can legitimately appear on two
  unrelated Accounts (e.g. a share account and a savings account at the same institution).

- **Transaction** — a single movement of money, as reported by Plaid. Identified by Plaid's
  `transaction_id`. Plaid may revise a Transaction in place (the pending-to-posted transition
  changes its amount, date or description) or move it to a different Account, without changing
  that id.

- **Natural key** — `(account_key, date, description, amount)`. A *description* of a
  Transaction, deliberately **not** an identity: two different Transactions can legitimately
  share one. Used for grouping and for spotting duplicate candidates, never to enforce
  uniqueness.

- **Genuine repeat** — two or more distinct Transactions sharing a natural key, all of them
  real. Ordinary in practice: repeated transit taps, or several charges split across a card's
  contactless limit for one purchase.

- **Duplicate** — one real-world movement of money stored more than once. Arises when the same
  Transaction is re-issued under a new `transaction_id` (an Item re-link), when one Account is
  visible through two Plaid Items, or when Plaid itself returns the same Transaction twice.

- **Flagged duplicate** — a Transaction the user has marked as a Duplicate. Plaid exposes no
  field distinguishing a Duplicate from a Genuine repeat, so this records a human judgement.
  Flagged Transactions are excluded from all analytics but retained, so the judgement is
  reversible.

- **Reconciliation** — trimming stored Transactions for a natural key down to the number Plaid
  currently reports for it. A natural key Plaid reports *none* of is left alone: Plaid's window
  rolls forward and drops history that remains real.
