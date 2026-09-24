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

- **Under-merge** — the opposite failure to an Account fork: two genuinely *different* Accounts
  end up represented by a single `accounts` row, because their identity keys
  `(official_name, account_subtype, account_type, mask)` happen to coincide. The account-fork
  warning the dashboard shows (see Account fork, above) cannot detect this case — it only catches
  the reverse, too many rows for one identity, never too few.

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

- **Budget period** — a calendar month a budget Cap applies to, written `YYYY-MM`. The unit the
  Budget tab is organised around.

- **Cap** — a per-category spending limit for one Budget period. A category with **no** Cap is
  *unbudgeted*; a category with a Cap of `0` is budgeted to spend nothing. These are different
  states and must never be conflated: the second is breached by any spend, the first cannot be
  breached at all.

- **Explicit cap / Inherited cap** — an *explicit* Cap was set for that month and is stored. An
  *inherited* Cap is the most recent explicit Cap from an earlier month, applying because no Cap
  was set for this one. Editing an inherited Cap creates an explicit Cap for the displayed month
  only; it never rewrites earlier months.

- **Canonical category** — one of the closed set of category names the taxonomy allows. Anything
  outside it is *free text*: a value stored before the set was closed, kept and reported rather
  than rewritten, because a wrong guess destroys a correction the user made deliberately.

- **Recurring stream** — a repeating charge recognised as one series: a merchant, a cadence, a
  predicted next date. The thing a person means by "a recurring charge", as opposed to the
  individual Transactions that make it up.

- **Stream override** — a user's hand-set recurring flag on a Transaction. Always wins over
  stream membership, and never cleared by the pipeline — the same guarantee Flagged duplicate and
  a user's category correction carry.

- **Mature stream / Early detection** — a *mature* Recurring stream has been seen at least three
  times; an *early detection* stream has been seen fewer, so its prediction is shown as lower
  confidence rather than asserted.

- **Savings goal** — an amount the user is saving toward, with an optional target date and a set
  of Accounts holding the money. Deliberately generic: a down payment, a car and an emergency
  fund are the same thing to the system.

- **Goal baseline** — the combined balance of a Savings goal's Accounts at the moment the goal
  was created. Progress is measured from it, so money already present when the goal started is
  not counted as progress toward it.

- **Pace basis** — which measurement a Savings goal's monthly rate was derived from: *balance*
  (observed growth in the linked Accounts) or *cashflow* (income minus expenses), used until
  there is enough balance history to measure growth. Always stated alongside the rate; a rate
  without its basis is a number the reader cannot judge.

- **Contested progress** — the part of a Savings goal's balance held in an Account another goal
  also claims. Overlap is allowed, because people do save for two things in one Account, but it
  is surfaced: otherwise two goals can each report being on track when the same money can only
  fund one.

- **Anomaly** — a statement that something has moved away from the user's own recent pattern,
  carrying the sentence it was derived from. A property of a Category in a period, or of a
  Recurring stream — never of a single Transaction.

- **Category drift** — an Anomaly reporting that a Category has spent materially more by this
  point in the month than it usually had by the same point in previous months.

- **Price creep** — an Anomaly reporting that a Recurring stream's amount has risen materially
  since its earlier occurrences.

- **Dismissal** — the user's judgement that an Anomaly is not worth acting on. Scoped to the
  period it was raised in: the same Anomaly in a later period is raised again, because a reason
  that explained one month does not explain the next.
