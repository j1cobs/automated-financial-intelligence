# ADR 0009: Plans as a base plus layered Event plans, closed amount forms, and one projection engine

## Status

Accepted (2026-10-20). Designed in a `/grill-with-docs` session over
`docs/research/budget-tab-best-practices.md`; to be implemented as PLAN.md Phases 43-46.

## Context

The household keeps a forward plan in a spreadsheet: assumptions with notes, a five-year projection with
lines that grow, lock or end, and scenarios compared side by side. The research found that no surveyed
budgeting tool (YNAB, Actual, Monarch, Copilot, Lunch Money, Firefly III) offers per-line growth rates or
line end dates in a monthly budget, and only Monarch offers named scenarios, on a paid tier.

The user was explicit that the feature must **not** model their spreadsheet: "general enough to be used for
any use case", and "all features must be applicable to any scenario". So the questions were what a generic
Plan is, how much formula power it gets, and how it relates to the forecast that already exists
(`analytics/forecast.py`, Phase 32).

## Decision

**Two kinds of Plan, combined as one base plus layers.** A *Full plan* describes the whole budget. An *Event
plan* describes only what changes: new costs, costs that stop, one-time costs, new income. A projection has
exactly one *Projection base*, either the Actual baseline or one Full plan, plus any number of Event plans
layered on it. So "my five-year plan plus the wedding plus the condo" is expressible, and two Event plans
compose without either knowing about the other.

**Inputs at two scopes.** Each Plan has its own named inputs (a price, a rate). *Household assumptions*
(inflation, income growth) belong to the household, so every Plan layered into one projection agrees on
them. A *Scenario* is a named set of overrides on one Plan's inputs and on Household assumptions. It
never adds or removes lines.

**Amounts come from a closed set of forms, not formulas.** A line amount is a number, an input, a percentage
of an input, an amount per occurrence times a count, or an Amortizing loan payment (fixed for a term,
re-amortized at a renewal-rate input). Every form renders as a sentence ("1% of Purchase price, per year").
There is no expression language. The **XLSX export is the escape hatch**: inputs are exported as live
cells with cached values, so anything the closed set cannot express can be done in Excel from the
export. The set grows by adding one tested form when a real line needs it.

**Timing comes from five frequency forms** (monthly; every N months from a start month; on listed months;
once in a month; spread evenly over a window), each with optional start and end months. **Growth** steps
once per plan year on amounts stated in plan-start dollars, at a rate that is a number or an input.

**One engine.** `analytics/projection.py` computes month by month and the Plans view shows years with a
drill-down into months. The Phase 32 forecast is re-expressed as a projection over the Actual baseline
with the active Plans layered on, over its existing 12-month window. Phase 32's rules (streams on
predicted dates, trailing medians, the 3-month minimum, the in-progress month excluded) become how the
Actual baseline is built. `tests/test_forecast.py` must pass unchanged across the refactor.

**Draft, Active, Archived.** Drafts are only explored. *Active* means committed: at most one Full plan
plus any number of Event plans. Active plans drive cap suggestions and plan-vs-actual. A Plan never writes
a cap itself: adopting a suggested amount writes an explicit cap through ADR 0005's path, one Category
at a time.

## Consequences

- The Budget tab's forecast starts to include active Event plans. A committed wedding shows up in the
  12-month cash-flow chart without anyone re-entering it.
- Phase 32's 36-month ceiling stays for the Budget tab forecast. Plans allow 1-10 years, so the engine takes
  its ceiling as a parameter rather than a module constant.
- A user who needs an exotic formula exports, edits in Excel and does not re-import. Round-tripping was
  deliberately left out.
- One-time lines track actuals through Tags, because one event's spending crosses Categories (a dress is
  still Shopping).

## Alternatives considered

- **Absolute plans only** (the spreadsheet's shape). Plans can't compose: a wedding and a condo would be two
  alternative futures, never one.
- **Delta plans only.** Can't express "my whole budget in five years" except as a pile of deltas against
  today.
- **One Plan kind with a "replaces baseline" flag.** Fewer nouns, but two replacing plans active at once
  has no clear meaning.
- **Free-form spreadsheet formulas.** The most flexible option, but the UI can't explain a formula back to
  the user, a typo fails silently, and it needs a parser. It would turn the app into a weaker Excel.
- **Keep the forecast and the plan projection as two engines.** They would disagree about the same month,
  and every rule would need testing twice.
- **Plans seed caps on activation.** Fast, but it rewrites caps the user set by hand. Suggest-and-adopt
  keeps ADR 0005's "an edit never rewrites what the user meant".
