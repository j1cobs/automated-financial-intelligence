# Domain glossary

- **Account** — a real account at a financial institution (a chequing account, a credit card, an
  investment account). Durable across Plaid Item re-links; the *same* Account should always be
  represented by exactly one row.

- **Account key** — the Plaid-issued, Item-scoped identifier used as the `accounts.account_key`
  primary key. *Not* durable: a Plaid Item re-link (e.g. after rotating access tokens) issues a
  new one for the same Account.

- **Manual account** — an Account the household keeps by hand (a cash wallet, a card no
  connection reaches). Its Transactions and balance are entered, edited and deleted by the user;
  syncing and Reconciliation never touch it, and no rule about Plaid Transactions applies to it.

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
  owner label, whichever connection happened to reveal it. An ingestion detail: per-person views
  use Account holder, never Owner.

- **Household member** — one of the people the household's finances belong to. The household is
  the unit a budget, a Plan and a Savings goal belong to; members only matter where money is
  attributed to a person.

- **Account holder** — who an Account belongs to: one Household member, or *Joint*. Set by the
  user once per Account. Spend and income in per-person views are attributed through it, so a
  joint account shows as its own slice rather than as whichever member's connection revealed it.

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

- **Windowed cap** — a Cap that covers a window of months instead of one (a calendar year, or N
  months from a start month), judged by spend-to-date against an even pace through the window. A
  Category's Cap is either monthly or windowed, never both.

- **Saved this month** — the actual amount behind Savings-class lines: the net balance growth of
  the Accounts nominated by Savings goals and Sinking funds. Money moving between the household's
  own Accounts (a credit-card payment, an internal transfer) is never spending and never income,
  so it can only show up here as a balance change on a nominated Account.

- **Explicit cap / Inherited cap** — an *explicit* Cap was set for that month and is stored. An
  *inherited* Cap is the most recent explicit Cap from an earlier month, applying because no Cap
  was set for this one. Editing an inherited Cap creates an explicit Cap for the displayed month
  only; it never rewrites earlier months.

- **Subcategory** — a user-defined child of exactly one Canonical category, drawn from a closed
  set the user curates. The hierarchy is exactly two levels deep: a Subcategory never has
  children of its own. Plaid's detailed category only *suggests* Subcategories; it is not one.

- **Unallocated slack** — the part of a Category's Cap not assigned to any of its Subcategories'
  Caps. A Category with no Cap of its own is capped at the sum of its Subcategories' Caps and has
  no slack. Spending in the Category that belongs to no Subcategory is charged against the slack.
  A Transaction lands in a Subcategory either because the user pinned its merchant there or
  because the Subcategory claims the Transaction's Plaid detailed category; the user's pin wins.

- **Excluded category** — a Category the user has placed outside the budget (taxes paid,
  business costs). Its spending is still recorded but never counts toward totals, Caps or Ratios.

- **Pending spend** — spending on Transactions Plaid has authorized but not yet posted. Counts
  against Caps, always shown as a separate "of which pending" figure, because it can still change.

- **Split** — one Transaction divided into parts, each with its own Category, Subcategory and
  Tags; the parts always sum to the Transaction. Budgets count the parts, never the whole.

- **Reimbursable** — spending the household expects to be paid back for. Kept out of spend while
  outstanding, and settled when matched to the repayment.

- **Shared spending** — the spending the household's members split between them: everything spent
  on a Joint Account, plus spending in Categories marked *shared* (wherever it was paid), adjusted
  by a per-Transaction override either way. Buying household groceries on a personal card is
  Shared spending.

- **Shared-cost settlement** — for Shared spending, each Household member's fair share compared
  with what they actually paid, and the running balance between members that results. The fair
  share comes from a household *share basis*: a preset (equal, proportional to Regular income)
  or a custom ratio. Spending on a Joint Account is paid by members in proportion to what they
  transferred into it. A transfer from one member's Account to another's settles part of the
  balance.

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

- **Sinking fund** — a cost that comes less often than monthly (an annual tax, an insurance
  premium, car repairs), saved for ahead by setting money aside every month in a nominated
  Account. Described by an amount, a cadence and the next due date. It has no balance of its own.

- **Required balance** — what all the Sinking funds on one Account should hold by today, given
  each fund's amount, cadence and next due date. Compared with the Account's real balance to say
  whether the funds are on track. Computed every time, never stored, so it cannot drift from the
  money that actually exists.

- **Line class** — a label from a small closed set used to subtotal budget Categories and plan
  lines. A label only: how a line changes over time comes from the line's own growth rate, end
  date and frequency, never from its class. The set is *Fixed* (contractual amounts), *Essential*
  (needed but varying), *Flexible* (discretionary) and *Savings* (money set aside before
  discretionary spending: Savings goals and Sinking funds).

- **Amortizing loan** — a line whose amount is the payment on a borrowed principal at a rate over
  an amortization period, fixed for a term and re-amortized at a renewal rate when the term ends.
  Generic: the same form covers any loan repaid in equal instalments.

- **Regular income** — income that arrives on a pattern: Recurring streams of income (salaries).
  The basis for "remaining" and every share-of-income figure. Measured net, as deposited.

- **Expected income** — income the user declares ahead of time because it is not Regular: a
  yearly bonus, contract work, a tax refund. Has an amount, an expected month or cadence, and a
  Household member. Never counted in "remaining" before it arrives; when a deposit arrives it is
  matched to the declaration and the declaration shows as received.

- **Allocation rule** — the user's standing split for Expected income when it arrives ("half to
  the emergency fund, the rest free"). Produces suggestions the user accepts; never moves money.

- **Plan** — a named, forward-looking description of the household's money over a horizon of
  years. Deliberately generic: nothing in a Plan knows what a wedding or a home is. Comes in two
  kinds, Full plan and Event plan.

- **Full plan** — a Plan that describes the whole budget: every income and spending line. Used as
  an alternative Projection base.

- **Event plan** — a Plan that describes only what changes: new costs, costs that stop, one-time
  costs, new income. Never stands alone; it is layered onto a Projection base, and several Event
  plans can be layered at once. Each of its lines either *adds* to the base or *replaces* the
  base's amount for one Category from its start month, which is how a cost that stops is
  expressed.

- **Projection base** — what a projection starts from: either the Actual baseline or exactly one
  Full plan. A projection is its base plus every Event plan layered on it. There is one projection
  engine: the Budget tab's forward forecast is a projection over the Actual baseline with the
  active Plans layered on.

- **Actual baseline** — the household's own pattern projected forward: Recurring streams at their
  predicted dates and amounts, plus each Category's recent typical spending for the rest.

- **Draft / Active / Archived plan** — a *draft* Plan is only explored: it can be layered into a
  projection but drives nothing. An *active* Plan is one the household has committed to living:
  it drives cap suggestions and plan-vs-actual. At most one Full plan is active at a time, plus any
  number of Event plans. An *archived* Plan is kept for its history and drives nothing.

- **Scenario** — a named set of overrides on one Plan's inputs and on Household assumptions,
  compared side by side with the Plan's other Scenarios under the same Projection base. A
  Scenario never adds or removes lines; it only changes the values lines are computed from.

- **Ratio** — a user-defined share of Regular income: chosen Categories, Subcategories or plan
  lines divided by Regular income (actual in the monthly budget, projected in a Plan), with an
  optional threshold the user sets. No threshold is
  built in: what counts as affordable is the household's call.

- **Plan input** — a named value a Plan's lines refer to (a purchase price, an interest rate, an
  inflation rate). Line amounts and growth rates can be stated in terms of inputs, so changing one
  input re-prices every line that uses it. A line amount is always one of a small closed set of
  forms that reads as a sentence ("1% of Purchase price, per year"); there are no free-form
  formulas.

- **Household assumption** — a Plan input that belongs to the household rather than to one Plan
  (inflation, income growth), so every Plan in a projection agrees on it.

- **Plan growth** — a line's growth rate applied in whole steps, once per plan year, to amounts
  stated in plan-start dollars. The rate is a number or a Plan input.

- **Tag** — a user-applied label on a Transaction, independent of its Category, so one event's
  spending can be followed across Categories without moving it out of them. How a one-time plan
  line finds its actual spending.

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
