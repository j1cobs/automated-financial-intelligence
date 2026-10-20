# Budget tab: budgeting best practices and feature research

*Research date: 2026-10-19; current-state sections updated against `dev` (913fdbc) on 2026-10-20. Scope: generic and region-neutral. Quebec and Canada rules are out of scope by request. Input for a grill-with-docs planning session.*

**How sources were verified.** Each claim links to its source.
- **[verified]** means the page or file was fetched directly.
- **[search-index]** means the page blocked direct fetching (Monarch's help center and Fannie Mae return HTTP 403) or was a PDF that could not be extracted (CFPB worksheets). The claim rests on the search engine's summary of that page. Treat it as likely but not confirmed.
- **[unverified]** means it could not be confirmed at all.
- YNAB's support center renders in the browser, so its article bodies could not be read. YNAB facts come from YNAB's marketing guides and its official OpenAPI spec instead.

---

## 0. Current app state (on `dev` at `913fdbc`, PLAN.md Phases 28–36)

The research ran against an older `main` and was updated afterwards to match `dev`. Read the ADRs below before planning, because they already settle several of the open questions in §7.

| Area | On `dev` | What that means for this research |
|---|---|---|
| Per-month caps | `budget_periods(category, period 'YYYY-MM', monthly_limit)`, migration 026. A month with no row **inherits** the most recent earlier cap ("carry-forward"). An absent cap is not a $0 cap. `DELETE /budgets/{category}?month=` reverts a month to its inherited cap. See **ADR 0005**. | Per-month limits and limit history are **done**. Carry-forward here means *cap inheritance*. It does not roll money over: ADR 0005 explicitly deferred envelope/YNAB rollover. The legacy `budgets` table now belongs only to the frozen Streamlit app. |
| Closed category set | `analytics/categories.py::canonicalize`. Caps are keyed on canonical categories, and the endpoint rejects free text. | Any user-defined subcategory needs its own closed set. It cannot be free text. |
| Budget tab UI | Month selector; each row **expands to a `pfc_detailed` breakdown** (read-only amounts); inherited caps are labelled with their source month; drift anomalies appear on the row; `GoalsSection` and `ForecastChart` sit on the same tab (Phase 29). | A read-only subcategory breakdown **exists**. Subcategories with their own *limits* do not. |
| API `pct` | Still `min(spent / limit, 1.0)` in `build_budget` | "How far over" is still not available (catalogue item 2). |
| Recurring streams | `recurring_streams` (migration 027), from Plaid `/transactions/recurring/get` or derived locally; each has `predicted_next_date`. See **ADR 0006**. | This is the basis for a bill calendar and for sinking funds. |
| Forecast | `analytics/forecast.py`: a forward cash-flow forecast from streams plus trailing medians (solid line) vs cap-held (dashed line). It needs 3 months of history (Phase 32). | A short-horizon behavioural forecast exists. A multi-year **plan projection** with growth rates does not. |
| Savings goals | `savings_goals` plus linked accounts (migration 028); progress = balance minus baseline; `pace()` always states its basis; `what_if(category, monthly_reduction)`. See **ADR 0008**. | Targets by date are **done**, in balance-based form. ADR 0008 **deferred an affordability calculator** (mortgage, taxes, condo fees). That is exactly the missing "Plans" piece. |
| Anomalies | Category drift and price creep (migration 029, **ADR 0007**) | Covers most of "alerts" in-app. |
| Export | No CSV/XLSX export, and no `openpyxl`, `xlsxwriter`, `xlsx` or `exceljs` dependency | Any export work starts from scratch. |

---

## 1. Budgeting methods and best practices

### 1.1 Zero-based / envelope budgeting (YNAB, Actual)
- **Assign only money you already have.** YNAB's Rule One says to give every dollar a job and budget only with dollars you actually have. Expected money such as a bonus or tax refund stays out until it arrives ([YNAB guide](https://www.ynab.com/guide/where-does-my-money-go)) [verified]. Actual Budget takes the same stance: "you can only budget money that you already have" ([Actual docs](https://actualbudget.org/docs/budgeting/)) [verified].
- **True expenses / sinking funds.** YNAB's Rule Two says to turn irregular costs into monthly amounts. Examples: car repairs at about $2,000/yr become $167/mo, and an $840 life insurance premium becomes $70/mo. If the amount is unknown, guess and adjust ([YNAB blog](https://www.ynab.com/blog/why-embracing-your-true-expenses-is-everything)) [verified]. The same article argues that many "emergencies" are predictable costs on an unpredictable schedule. Funding them ahead keeps the emergency fund for real emergencies [verified].
- **Roll with the punches.** Rule Three says to move money between categories when life changes, and not to treat a budget edit as failure ([YNAB guide](https://www.ynab.com/guide/where-does-my-money-go)) [verified].
- **Age your money.** Rule Four is to live on last month's income ([YNAB blog via search](https://www.ynab.com/blog/the-key-to-reducing-your-money-stress)) [search-index]. Actual has a matching "Hold for next month" feature, plus auto-hold for the next 12 months ([Actual docs](https://actualbudget.org/docs/budgeting/)) [verified].

### 1.2 Rule-of-thumb splits (50/30/20)
- CFPB teaching material splits take-home pay into 50% needs, 30% wants and 20% savings. It warns that the need/want line is personal and that the rule is "only one rule to live by" ([CFPB analyzing-budgets guide](https://files.consumerfinance.gov/f/documents/cfpb_building_block_activities_analyzing-budgets_guide.pdf), [CFPB "My spending rule to live by"](https://files.consumerfinance.gov/f/201603_cfpb_rules-to-live-by_my-spending-rule-to-live-by.pdf)) [search-index].
- **For the app:** show this as a *reference ratio* next to real figures, not as a rule the app enforces.

### 1.3 Pay yourself first
- MyMoney.gov: "each pay period, before you are tempted to spend money, commit to putting some in a savings account" ([MyMoney.gov](https://www.mymoney.gov/saveandinvest)) [verified].
- CFPB recommends automatic recurring transfers and split direct deposit ([CFPB blog](https://www.consumerfinance.gov/about-us/blog/looking-easy-way-save-money-make-it-automatic/)) [search-index].
- **For the app:** savings and plan contributions should be budget *lines* that sit above discretionary spending, not whatever is left at month end.

### 1.4 Fixed vs non-monthly vs flexible
- Monarch's default "Flex budgeting" uses three buckets ([Monarch help](https://help.monarch.com/hc/en-us/articles/32125337244052-Understanding-Flex-Budgeting) [search-index]; [Monarch blog](https://www.monarch.com/blog/fixed-flex-spending-what-it-is-and-how-to-get-started) [verified]):
  - **Fixed:** predictable monthly costs such as rent or mortgage, insurance, utilities and subscriptions.
  - **Non-monthly:** costs that come at least once a year, also called sinking funds.
  - **Flexible:** groceries, dining, shopping and similar.
  - Formula: `Income − Fixed − Non-monthly − Goals = Flex number`. Example: $6,400 − $2,000 − $1,000 − $200 = $3,200 [verified].
- Monarch suggests splitting a mixed category, for example "Child Activities – Monthly" and "– Seasonal" [search-index].
- CFPB's toolkit separates *unexpected* expenses from *periodic* expenses, which are predictable but occasional (car insurance, property taxes). It separates income into **Regular / Irregular / Seasonal / One-time** ([CFPB YMYG toolkit](https://files.consumerfinance.gov/f/documents/cfpb_your-money-your-goals_financial-empowerment_toolkit.pdf)) [search-index]. The toolkit includes a "Planning for life events and large purchases" tool ([CFPB toolkit page](https://www.consumerfinance.gov/consumer-tools/educator-tools/your-money-your-goals/toolkit/)) [verified].
- **The user's workbook FIXED / VOLATILE / CONTROLLABLE / TEMPORARY buckets** go further than Monarch's three. They classify lines by *how they change over time* (locked, grows by a rate, held constant, ends on a date), not only by how often they recur. Nothing in the surveyed tools models that. It is the gap a "Plans" feature would fill.

### 1.5 Emergency fund
- CFPB says the target depends on your situation: size it from past surprise costs, and "even a small amount" helps. It suggests putting all or part of a tax refund or other windfall into the fund, and rebuilding after you use it ([CFPB guide](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/)) [verified].
- MyMoney.gov: "at least three months" before investing ([MyMoney.gov](https://www.mymoney.gov/saveandinvest)) [verified].
- CFPB home-buying guidance: keep "at least three to six months' worth of expenses" as a cushion when working out cash available for closing ([CFPB down payment](https://www.consumerfinance.gov/owning-a-home/prepare/determine-your-down-payment/)) [verified].

### 1.6 Rollover / carryover

| Tool | Leftover money | Overspending |
|---|---|---|
| Actual (envelope) | Rolls into the category next month | Taken from next month's "To Budget"; the category resets to 0, unless you choose "Rollover overspending" ([docs](https://actualbudget.org/docs/budgeting/)) [verified] |
| Actual (tracking) | Does **not** carry over by default; you opt in per category ([docs](https://actualbudget.org/docs/getting-started/tracking-budget)) [verified] | Same, opt-in |
| Lunch Money | Per category: same category / general pool / nothing ([docs](https://support.lunchmoney.app/guides/budgeting/step-2-setting-up-your-budget)) [verified] | Carries forward the same way |
| Copilot | Global toggle with a "first month with a rollover"; cumulative; individual categories can be excluded ([help](https://help.copilot.money/en/articles/3790828-budget-rollovers)) [verified] | Carries into the next month |
| Firefly III | Auto-budget modes: reset, grow ("add every period") and "correct for overspending" (example: 25 budget, 35 spent, next month 15; floor of 1 if you spend more than double) ([docs source](https://github.com/firefly-iii/docs/blob/main/docs/docs/how-to/firefly-iii/finances/budgets.md)) [verified] | The adjusted mode subtracts it |
| Monarch | Rollover per category or group; required for Non-monthly with a frequency and target, e.g. $600 every 6 months = $100/mo ([help](https://help.monarch.com/hc/en-us/articles/4411119762196-Rollover-budget-feature)) [search-index] | [unverified] |

**Pattern:** rollover is usually **opt-in per category**, needs a **start month**, and is **cumulative**. Fixed bills are usually excluded.

### 1.7 Review cadence
- Actual's workflow: import and categorize transactions regularly, then create next month's budget at month end ("Copy last month's budget") ([docs](https://actualbudget.org/docs/budgeting/)) [verified].
- CFPB's bill calendar lists every bill's due date and payday in one monthly view, and says to remember bills due every few months or once a year ([CFPB toolkit](https://files.consumerfinance.gov/f/documents/cfpb_your-money-your-goals_financial-empowerment_toolkit.pdf)) [search-index].
- Monarch Forecasting is meant to be "directionally" right. Its default expense baseline does not update automatically, so the user has to revisit it ([help](https://help.monarch.com/hc/en-us/articles/48344305092244-Forecasting-in-Monarch)) [search-index]. Plans need an explicit re-review step.

### 1.8 Buffers and contingency
- CFPB says closing costs typically run 2–5% of the price; build in a cushion because early estimates are rough ([CFPB](https://www.consumerfinance.gov/owning-a-home/prepare/determine-your-down-payment/)) [verified].
- Maintenance reserve: Fannie Mae suggests 1–4% of home value per year, leaning toward 4% for homes over 30 years old, then refining from actual spending ([Fannie Mae](https://yourhome.fanniemae.com/own/how-build-your-maintenance-and-repair-budget)) [search-index]. CFPB's worksheet calls 1% a common rule of thumb ([CFPB worksheet](https://files.consumerfinance.gov/f/documents/cfpb_buying-a-house_monthly-payment_worksheet.pdf)) [search-index]. This matches the workbook's 1%/yr line.
- **Housing cost as % of income, as a generic concept:** HUD's long-standing affordability benchmark is housing costs at or below 30% of income ([HUD PD&R](https://www.huduser.gov/portal/pdredge/pdr-edge-frm-asst-sec-072425.html), [HUD 30% study](https://www.huduser.gov/portal/publications/trends_hsg_costs_85-2005.pdf)) [search-index]. Fannie Mae's calculator uses 25–30% of gross income [search-index]. CFPB defines DTI as monthly debt payments ÷ gross monthly income. Its example: $2,000 ÷ $6,000 = 33% ([CFPB](https://www.consumerfinance.gov/ask-cfpb/what-is-a-debt-to-income-ratio-en-1791/)) [verified]. **For the app:** let the threshold be user-set, and record whether it is measured against gross or net income. The workbook uses net.

### 1.9 Non-guaranteed income kept separate
- YNAB: bonus and tax-refund money is not budgeted until it arrives ([YNAB guide](https://www.ynab.com/guide/where-does-my-money-go)) [verified].
- CFPB: separate regular income from irregular, seasonal and one-time income [search-index], and decide ahead what share of a tax refund to save ([CFPB](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/)) [verified].
- This backs the workbook's choice to keep bonus and refund **out** of the monthly budget.

---

## 2. How leading tools model budgets

| Capability | YNAB | Actual Budget | Monarch | Copilot | Lunch Money | Firefly III |
|---|---|---|---|---|---|---|
| **Hierarchy** | Group → category. The API's `CategoryGroup` has no nesting ([OpenAPI spec](https://api.ynab.com/papi/open_api_spec.yaml)) [verified] | Group → category; one income group ([docs](https://actualbudget.org/docs/budgeting/categories)) [verified]. A nested-groups PR [#5268](https://github.com/actualbudget/actual/pull/5268) was **closed unmerged** [verified] | Group → category; budget "By group" or "By category" per group ([help](https://help.monarch.com/hc/en-us/articles/18345219809940-Group-Budgeting)) [search-index] | Group → category, plus a group "unassigned budget" ([help](https://help.copilot.money/en/articles/3767655-groups-of-categories)) [verified] | Group → category; budget by group or by category ([docs](https://support.lunchmoney.app/guides/budgeting/step-2-setting-up-your-budget)) [verified] | Budgets and categories are **separate, flat** concepts: "categories cannot be 'monetized'" ([docs](https://github.com/firefly-iii/docs/blob/main/docs/docs/explanation/financial-concepts/budgets.md)) [verified] |
| **Parent vs child limits** | Groups hold no amount [verified, spec] | Groups show totals only [verified] | By-group: category actuals summed against one group budget [search-index] | Group = subcategory budgets + unassigned (exact formula not stated) [verified] | Group budget optional: if unset it **equals the sum**; you can set it **larger** for slack [verified] | n/a |
| **Rollover** | Balances carry forward (envelope model) [unverified detail] | Yes (§1.6) | Per category or group [search-index] | Global plus per-category exclusion | Per category, three modes | Auto-budget modes |
| **Targets / goals** | `goal_type`: TB (balance), TBD (balance by date), MF (monthly funding), NEED (plan your spending; set aside vs refill), DEBT; with `goal_cadence`, `goal_target_date`, `goal_under_funded`, `goal_snoozed_at` ([spec](https://api.ynab.com/papi/open_api_spec.yaml)) [verified] | Templates in category notes: `#template 50`, `… up to 100`, `#template 10000 by 2025-12` (→ $833.33/mo), `repeat every year`, `spend from`, percent of income, average of the last N months, priorities ([docs source](https://github.com/actualbudget/docs/blob/master/docs/experimental/goal-templates.md)) [verified, experimental] | Save-up goals: target amount + date + monthly contribution gives on track / ahead / at risk; optional growth rate per account ([help](https://help.monarch.com/hc/en-us/articles/44373182867476-Using-Save-Up-Goals), [growth rates](https://help.monarch.com/hc/en-us/articles/47822256713236-Growth-Rates-in-Save-Up-Goals)) [search-index] | [unverified] | Rollover to the same category used as a sinking fund ([blog](https://lunchmoney.app/blog/how-to-track-savings-goals-with-rollovers)) [search-index] | Piggy banks tied to one asset account ([docs](https://github.com/firefly-iii/docs/blob/main/docs/docs/explanation/financial-concepts/piggy-banks.md)) [verified] |
| **Flex / fixed split** | – | Tracking vs envelope modes [verified] | Flex budgeting: Fixed / Non-monthly / Flex [verified blog] | "Optional budgeting" compares to last month ([help](https://help.copilot.money/en/articles/6282850-optional-budgeting)) [search-index] | – | – |
| **Forecast / what-if** | "Edit Plan" compares total targets with expected income ([help](https://support.ynab.com/plan-and-adjust-with-edit-plan-and-cost-to-be-me-ByR7vpqPyx)) [search-index] | "Copy until year end" for forward months (tracking mode) [verified] | **Forecasting** (Plus tier): 12-month actuals as baseline, editable assumptions (e.g. 3% inflation), life events, **multiple named scenarios, duplicate, compare two side by side** ([help](https://help.monarch.com/hc/en-us/articles/48344305092244-Forecasting-in-Monarch)) [search-index] | "Rebalance" keeps the total and redistributes ([help](https://help.copilot.money/en/articles/6206302-rebalancing-your-budget)) [search-index] | – | – |
| **Multi-month view** | [unverified] | Multi-month budget columns [verified] | Calendar/forecast view ([help](https://help.monarch.com/hc/en-us/articles/360051885292-Budget-Forecast)) [search-index] | Per-month edits; rollovers not shown for future months [verified] | Custom periods; changing the period **deletes existing budgets** [verified] | Daily to yearly periods; mixing yearly and monthly double-counts [verified] |
| **Sharing** | YNAB Together: members with their own logins ([help](https://support.ynab.com/en_us/ynab-together-B1nS78Cki)) [search-index] | [unverified] | Couples/households, shared views [search-index] | [unverified] | Unlimited collaborators with full access [search-index] | – |
| **Export** | Full plan export, one-way, no re-import ([help](https://support.ynab.com/en_us/how-to-export-plan-data-Sy_CouWA9)) [search-index] | Export Data zip (backup) ([docs source](https://github.com/actualbudget/docs/blob/master/docs/backup-restore/backup.md)) [verified] | Transactions CSV only; budgets cannot be imported, and no budget export was found [search-index] | Transactions CSV, **includes Account Mask** ([help](https://help.copilot.money/en/articles/5944414-exporting-your-transaction-data)) [verified] | Transactions CSV with Category Group + Category columns ([help](https://support.lunchmoney.app/finances/transactions/other-features)) [verified] | CSV via CLI, including `--export-budgets` and `--export-piggies` ([docs source](https://github.com/firefly-iii/docs/blob/main/docs/docs/tutorials/firefly-iii/exporting-data.md)) [verified] |

**Takeaways**
1. **Every surveyed tool uses exactly two levels** (group → category). Nesting deeper is a common request (Actual [#1320](https://github.com/actualbudget/actual/issues/1320), [#3320](https://github.com/actualbudget/actual/issues/3320)), but no surveyed tool has shipped it [verified].
2. **No tool exports a budget-vs-actual sheet with assumptions.** Exports are transaction dumps or backups. A shareable plan workbook would be a real differentiator.
3. Long-range "plans" exist only in Monarch Forecasting (net-worth scale, paid tier) and as goal-by-date math (YNAB TBD, Actual `by`). Nobody offers per-line growth rates or line end dates in a monthly budget.

---

## 3. Subcategory recommendation

**Options**

| Option | Pros | Cons |
|---|---|---|
| A. Flat (today) | Simple | Cannot express "Housing → condo fees / insurance / electricity" |
| B. **Two levels: group → category** | Matches every surveyed tool; maps onto Plaid PFC `primary → detailed` (17 primary, ~104 detailed per ADR 0004) | Need to decide how parent and child limits relate |
| C. Arbitrary tree | Most expressive | No surveyed tool ships it; Actual's attempt was closed; recursive aggregation and UI cost |

**Recommendation: Option B.** The current canonical category (PFC primary, or a user override) becomes the **group**. Optional child **subcategories** sit under it: either a PFC detailed value, or a user-defined bucket mapped through merchant memory. Keep raw `pfc_detailed` as a *suggestion source*, not as the forced child list, because ADR 0004 already judged ~104 values too granular.

**Parent and child limits.** Use Lunch Money's model, which is the clearest documented one [verified]:
- If no group limit is set, the group limit is the **sum** of its child limits.
- If a group limit is set and it is ≥ the sum, the gap is **unallocated slack**. That is the same as Copilot's group "unassigned budget" [verified] and Monarch's "Unallocated Flexible Budget" [search-index].
- If a group limit is set below the sum, show a validation warning.
- Spending in the group with no subcategory counts against the slack. This is how PFC rows with no user-chosen child would work.

**Implementation notes**
- On `dev`, caps live in `budget_periods` (ADR 0005), keyed on the closed canonical category set. Child limits need a nullable `subcategory` column on `budget_periods`, or a sibling table. They also need a closed subcategory set, for the same orphan-row reason ADR 0005 gives for categories.
- `pct` should stop being capped at 1.0 if the UI is going to show "120% of limit".

---

## 4. Plans and forward budgeting

### 4.1 Patterns from sources
- **Lines due by a date** (YNAB TBD; Actual `#template 10000 by 2025-12` gives an even monthly amount, recalculated as the balance changes) [verified]. This covers the wedding fund and the down-payment fund.
- **Recurring non-monthly lines** (Actual `repeat every year` and `repeat every 6 months`; Monarch Non-monthly frequency + target) [verified / search-index]. This covers taxes, insurance and the annual pet permit.
- **Spend-from windows** (Actual `by 2024-12 spend from 2024-03`) [verified]. This covers costs paid in pieces before the deadline, such as wedding deposits.
- **Assumptions as editable inputs, plus named scenarios compared side by side** (Monarch Forecasting: editable inflation, life events, duplicate a scenario, compare two) [search-index].
- **Growth rates.** Monarch applies them to goal *accounts* [search-index]. Applying a rate per *expense line* has no precedent in the surveyed tools. It is new design work.
- **Notes per line.** Actual stores Markdown notes on categories [verified]. YNAB has a `note` field on categories [verified, spec].

### 4.2 Data model that can express the workbook

```
plan (id, name, status: draft|active|archived, start_month, horizon_years, notes)
plan_input (plan_id, key, value, unit, note, source_url)   -- purchase_price, rate, amortization, partner incomes...
plan_line (plan_id, label, bucket: FIXED|VOLATILE|CONTROLLABLE|TEMPORARY|WINDFALL|ONE_TIME,
           amount, frequency: monthly|annual|per_session|once, start_month, end_month NULL,
           growth_rate NULL, formula_ref NULL (e.g. "1% * purchase_price"),
           linked_category NULL, note, source_url)
plan_scenario (plan_id, name, overrides JSON)               -- e.g. {"down_payment_pct": 0.10}
```

How each part of the workbook maps:
- **Assumptions sheet** maps to `plan_input` and `plan_line`, with `note` and `source_url` on every row.
- **5-year projection** is *computed* from the lines and is not stored:
  - each year's amount is `amount × (1+growth)^(year−1)`;
  - TEMPORARY lines drop out after `end_month`;
  - FIXED lines stay flat for the term.
  - Output: subtotals per bucket, total per month, % of net income, "remaining", ×12 totals, cumulative change vs year 1, and a 5-year sum.
- **WINDFALL lines** (bonus, tax refund) are projected in their own block. They are never part of "remaining per month", which applies §1.9.
- **Scenarios sheet** maps to `plan_scenario` overrides. The view shows one column per scenario: financing, cash at signing, housing cost per month, housing % of income, housing+living %, remaining, and total liquidity (closing + wedding).
- **Mortgage payment** is a derived line: a standard amortization formula from price, down payment, rate and amortization. The app's job is only the arithmetic. Lender and insurance rules are out of scope.

### 4.3 Plan vs actual
- When a plan becomes **active**, each `plan_line` that has a `linked_category` shows the planned monthly amount for the current year next to the real spend from the existing cascade.
- An option is to *seed* `budget_periods` caps from the plan, starting at the plan's start month and relying on inheritance after that. This links the forward plan to monthly tracking.
- One-time lines track their cumulative actual spend against the line total. For tagging those transactions, a plan tag per transaction is one approach (Copilot and Lunch Money both use tags separately from categories) [verified, Lunch Money export has Tags].

---

## 5. Export and sharing

### 5.1 CSV vs XLSX

| | CSV | XLSX |
|---|---|---|
| Spec | RFC 4180 (**Informational**, not a standard) ([RFC 4180](https://www.rfc-editor.org/rfc/rfc4180)) [verified] | ECMA-376 5th ed. = ISO/IEC 29500 ([Ecma](https://ecma-international.org/publications-and-standards/standards/ecma-376/)) [verified] |
| Multiple sheets (assumptions / projection / scenarios) | No: one file per table | Yes |
| Formulas, number formats, notes | No | Yes |
| Accents (French) | Need a UTF-8 BOM for Excel | Native Unicode |
| Re-importable by other tools | Best | Good |

**Recommendation:**
- **CSV** for the monthly budget-vs-actual table, because it is simple and portable.
- **XLSX** for plans, because they need several sheets and notes.

### 5.2 RFC 4180 rules ([RFC 4180 §2](https://www.rfc-editor.org/rfc/rfc4180)) [verified]
- End each record with CRLF.
- An optional header row comes first.
- Separate fields with commas. Each row should have the same field count, with no comma after the last field.
- Quote a field if it contains a comma, a double quote or a line break. Inside a quoted field, write a double quote as two double quotes (`""`).
- The MIME type is `text/csv` with optional `charset` and `header` parameters.
- **Locale catch [unverified for French Excel specifically]:** Excel in locales that use a decimal comma often expects `;` as the separator. Write plain numbers (`1234.56`) and test with the user's Excel. XLSX avoids the problem.

### 5.3 UTF-8 BOM
- Microsoft: a UTF-8 CSV opens correctly in Excel when saved **with a BOM**. Otherwise the user has to go through Data > From Text/CSV ([Microsoft Support, DE](https://support.microsoft.com/de-de/office/ordnungsgem%C3%A4%C3%9Fes-%C3%B6ffnen-von-csv-utf-8-dateien-in-excel-8a935af5-3416-4edd-ba7e-3dfd2bc4a032)) [verified].
- The BOM bytes are `EF BB BF` (Python: `encoding="utf-8-sig"`). Without it, "Épicerie" shows up garbled ([MS Q&A](https://learn.microsoft.com/en-us/answers/questions/5104482/how-to-open-csv-file-encoded-with-utf-8-with-excel)) [search-index].

### 5.4 CSV / formula injection ([OWASP](https://community.owasp.org/attacks/CSV_Injection)) [verified]
- Dangerous leading characters: `=`, `+`, `-`, `@`, tab (0x09), CR (0x0D), LF (0x0A), and full-width `＝＋－＠`.
- OWASP's mitigation:
  1. Wrap every field in double quotes.
  2. Put a single quote `'` in front of any field that starts with a dangerous character.
  3. Escape each double quote by doubling it.
- An alternative that Excel resists better is a leading tab. Its downside is that it can break programmatic import.
- OWASP warns that sanitizing only the first character is not enough, because separators and quotes can start a new cell.
- **Why it applies here:** merchant names and descriptions come from Plaid and banks. They are external text and could begin with `=` or `@`.
- **Negative numbers:** apply the rule only to *text* cells. Write numeric amounts as numbers. In XLSX, use typed numeric cells, so `-42.10` stays a number.

### 5.5 Formulas vs values in XLSX
- None of the four candidate libraries calculates formulas:
  - **XlsxWriter** stores `0` as the cached result and flags Excel to recalculate on open. Viewers without a calculation engine (some mobile apps, PDF converters) show `0` unless you pass the computed `value` ([XlsxWriter docs](https://xlsxwriter.readthedocs.io/working_with_formulas.html)) [verified].
  - **openpyxl** "never evaluates formula". `data_only=True` only reads the value Excel cached last time ([openpyxl docs](https://openpyxl.readthedocs.io/en/3.1/simple_formulae.html)) [search-index].
  - **SheetJS** "will not automatically compute formula results" but can write both `f` and a cached `v` ([SheetJS docs](https://docs.sheetjs.com/docs/csf/features/formulae)) [verified].
  - **ExcelJS** supports `{ formula, result }` ([README](https://github.com/exceljs/exceljs)) [verified].
- **Recommendation:** compute every number in Python, which is the source of truth and already tested. Write **formula + cached result** for the cells a user would want to tweak (inputs → projection), so the file works in viewers *and* stays live in Excel. A "values only" toggle covers the read-only case.

### 5.6 Libraries

| Library | Side | License | Notes |
|---|---|---|---|
| XlsxWriter 3.2.9 | Server (Python) | BSD-2-Clause ([PyPI](https://pypi.org/project/XlsxWriter/)) [verified] | Write-only; rich formatting, comments, data validation |
| openpyxl 3.1.5 | Server | MIT ([PyPI](https://pypi.org/project/openpyxl/)) [verified] | Read and write; useful later for *importing* the user's existing workbook |
| SheetJS CE 0.20.3 | Client | Apache-2.0 [verified] | Install from the SheetJS CDN tarball. The npm `xlsx` package is stuck at 0.18.5 ([SheetJS install](https://docs.sheetjs.com/docs/getting-started/installation/frameworks)) [verified]. Styling is a Pro feature ([SheetJS docs](https://docs.sheetjs.com/docs/)) [verified] |
| ExcelJS 4.4.0 | Client or Node | MIT [verified] | Latest release 2023-10-19, last push 2025-01-21 [verified via GitHub API], so maintenance is slowing |

**Fit for this repo: server-side XlsxWriter, with stdlib `csv` for CSV.**
- The view models already live in `api/viewmodels.py`.
- An export endpoint can reuse them and the `dataload` cache.
- It adds no frontend bundle weight.
- It keeps the CSV-injection sanitizer in one tested Python function.

### 5.7 What a shareable export should contain
- **Include:**
  - Title, plan or month, **generated-at timestamp**, currency, filters applied.
  - Assumptions with notes and source links.
  - Per-line planned / actual / variance.
  - Bucket subtotals, % of income, remaining.
  - A windfall block kept apart from the monthly figures.
  - A scenario comparison.
- **Exclude:** account numbers, masks, `account_key`, Plaid IDs, `transaction_hash` and raw descriptions. Use aggregates only, unless the user opts into a transactions sheet.
  - Copilot's export ships the account mask [verified]. This app's logging rules already treat masks as sensitive (CLAUDE.md, ingestion section).

---

## 6. Feature catalogue for the Budget tab

Effort key: **S** is about a day, **M** is a few days with a migration and API change, **L** is a week or more.

| # | Idea | What it does | Why (source) | Effort | Replaces in the workbook |
|---|---|---|---|---|---|
| 1 | **Totals header** | Total budgeted, total spent, income this month, "remaining", % of income | Monarch flex-number formula [verified]; CFPB cash-flow budget [search-index] | S | Projection: total monthly, net income, % consumed, remaining |
| 2 | **Uncapped % and over-by amount** | Remove `min(..., 1.0)`; show "+$84 (112%)" | Existing code limitation | S | – |
| 3 | **CSV export of budget vs actual** | RFC 4180, UTF-8 BOM, OWASP sanitizing | §5 | S | Manual copying |
| 4 | **Subcategories (2 levels)** | Group = current category; child lines; sum-or-larger parent rule | §3; Lunch Money [verified], Copilot [verified] | M | Assumptions line items under a heading |
| 5 | **Bucket classification** | Tag each category or line as Fixed / Volatile / Controllable / Temporary (and Non-monthly) with bucket subtotals | Monarch Flex [verified]; CFPB periodic expenses [search-index] | S–M | Projection bucket rows and subtotals |
| 6 | **Notes per line** | Free text plus an optional source URL | Actual category notes [verified]; YNAB `note` [verified] | S | Notes/justification column |
| 7 | **Sinking funds / non-monthly lines** | Annual or per-N-month amount → monthly set-aside, with balance progress | YNAB Rule Two [verified]; Actual `repeat every year` [verified]; Monarch Non-monthly [search-index] | M | Annual→monthly conversions (taxes, permit) |
| 8 | **Per-month limits and history** | Add a `month` (or effective-from) column so limits can differ by month and past months keep their limit | Copilot per-month edits [verified]; Actual "Copy last month" [verified] | M | – (needed for 9 and 13) |
| 9 | **Rollover (opt-in per category)** | Leftover or overspend carries forward from a start month; cumulative | §1.6 (all tools) | M | Reserve tracking |
| 10 | **Income vs windfall separation** | Mark income sources as regular or non-guaranteed; windfalls stay out of "remaining" and show in their own block | YNAB Rule One [verified]; CFPB income types [search-index] | S–M | Non-guaranteed windfalls block |
| 11 | **Targets by date** | "$X by YYYY-MM", where the monthly need is recalculated from the current balance; on track / at risk | YNAB TBD [verified]; Actual `by` [verified]; Monarch status [search-index] | M | Wedding budget, emergency-fund target |
| 12 | **Plans (named, server-side)** | Inputs with notes, lines with frequency, start and end dates, growth rate and bucket; draft/active status | §4 | L | Whole Assumptions sheet |
| 13 | **Multi-year projection** | Computes years 1..N from the plan, with growth and end dates; ×12, cumulative change, N-year total | §4.2 | M (after 12) | 5-year projection sheet |
| 14 | **Scenarios** | Override inputs (e.g. down payment 5/10/15/20%) and compare columns side by side | Monarch Forecasting scenarios [search-index] | M (after 12) | Scenarios sheet |
| 15 | **Ratios panel** | Housing % of income and housing+living %, with a user-set threshold (reference: HUD 30%) | HUD [search-index]; CFPB DTI [verified] | S (after 12) | Scenario % rows |
| 16 | **Plan vs actual** | Active plan lines linked to categories; planned vs real per month; can seed `budget_periods` | §4.3 | M | Manually checking the plan against reality |
| 17 | **XLSX plan export** | Assumptions / Projection / Scenarios sheets, formulas with cached values, notes as comments, generated-at, no masks | §5.5–5.7 | M | Sharing the workbook |
| 18 | **Budget templates** | Start from 50/30/20, "copy last month", "average of last N months", or "use the plan" | CFPB 50/30/20 [search-index]; Actual average template [verified] | S–M | Setting up first limits |
| 19 | **Alerts** | Flag a category at ≥X% of limit, or projected EOM over limit; a target falling behind | Monarch at-risk status [search-index]; existing EOM projection | M | – |
| 20 | **Rebalance** | Shift over-budget amounts into categories with slack, keeping the total fixed | Copilot Rebalance [search-index]; YNAB Rule Three [verified] | S–M | – |
| 21 | **Bill calendar** | Due dates of recurring lines against paydays | CFPB bill calendar [search-index] | M | – |
| 22 | **Calendar-based temporary lines** | A per-session cost tied to a real calendar of sessions (tuition), not a flat monthly amount | Actual `repeat every N` with `starting` [verified] | M | Tuition session calendar |
| 23 | **Copy budget forward / to year end** | Bulk-fill future months | Actual "Copy until year end" [verified] | S (after 8) | – |
| 24 | **Snooze a month** | Skip a line or target for one month (already paid, low month) | YNAB snooze [search-index]; `goal_snoozed_at` [verified] | S | – |

### Status on `dev`

| Status | Items |
|---|---|
| **Done** | 8 (per-month caps with inheritance, ADR 0005); 11 (savings goals with pace and what-if, ADR 0008); 23 (made unnecessary by inheritance: a cap holds until it is changed) |
| **Partly done** | 4 (read-only `pfc_detailed` breakdown per row; child *limits* not built); 13 (forward cash-flow forecast exists; a multi-year plan projection does not); 19 (drift and price-creep anomalies in-app, ADR 0007; no threshold alerts on caps); 21 (recurring streams carry `predicted_next_date`, ADR 0006; no calendar view) |
| **Explicitly deferred** | 9 (envelope rollover, ADR 0005 "Alternatives"); the affordability calculator inside 12/15 (ADR 0008 "Consequences") |
| **Not started** | 1, 2, 3, 5, 6, 7, 10, 12, 14, 15, 16, 17, 18, 20, 22, 24 |

**Suggested order, given `dev`:** 1, 2, 3 → 5, 6 → 4 (child limits) → 7, 10 → 12 → 13, 14, 15 → 16, 17. The rest come later. Item 12 is where ADR 0008's deferred affordability calculator would land. It should reuse savings goals, so the down-payment target is a goal, and the forecast, rather than duplicate them.

---

## 7. Open questions for the planning / grilling session

1. **Subcategory depth and source.** Strictly two levels? Should children come from Plaid `pfc_detailed`, from user-defined buckets, or both? How do existing merchant-memory overrides map to a child?
2. **Parent/child limit rule.** Use sum-or-larger with slack (recommended), or independent caps? Does unassigned group spending count against the slack?
3. **Month dimension.** *Settled on `dev` by ADR 0005*: one explicit row per month that was set, inherited forward, and history is never rewritten. The remaining question is whether child limits (item 4) and plan-seeded caps (item 16) follow the same inheritance rule.
4. **Rollover semantics.** ADR 0005 deferred envelope rollover because it "only pays off under daily discipline". Is that still the right call, or do sinking funds (item 7) need a per-category balance after all? Sinking funds could instead track a savings goal (ADR 0008), with no budget-level balance.
5. **Envelope vs tracking.** Should the app stay a *tracking* budget, as today (limits as caps), or move toward "assign only money you have"? Most features above assume tracking plus sinking funds.
6. **Where plans live.** Server-side Postgres tables (recommended: survives devices, can be shared and exported) or client-only? Is there one household with two partners, and does the second partner need a login?
7. **Plan to budget link.** Does activating a plan *overwrite* `budget_periods` caps, *suggest* them, or only show a comparison?
8. **Growth model.** A simple annual rate compounding on plan-year boundaries, or on calendar years? Monthly granularity or annual steps? Are rates per line, or shared inputs (e.g. an "inflation" input reused by several lines)?
9. **Mortgage scope.** Is a fixed-rate amortization formula enough, with renewal and rate changes left out, so "FIXED, locked for term" means only the first term?
10. **Income basis.** Are % of income ratios on net or gross income? How should partners' incomes, raises and bonus tax rates be entered: as plan inputs, or taken from real tracked income?
11. **Windfalls.** Should a windfall that actually arrives be allocated to a plan line (e.g. emergency fund), or only reported?
12. **Export formulas vs values.** Live formulas with cached values (recommended), values only, or both as an option? Should the XLSX be re-importable to round-trip edits made in Excel?
13. **CSV separator and locale.** Is the comma (RFC 4180) fine, or does the user's French Excel need `;`? This needs a test on the user's machine.
14. **Export privacy.** Aggregates only by default? Should an opt-in transactions sheet exist at all, and must it always strip masks and IDs?
15. **Interaction with the Streamlit freeze.** All new work goes into `web/` and `api/`. Does `app/dashboard.py`'s budget section stay as it is, even after the schema grows?
16. **Alerts delivery.** In-app only, or email/push later? The latter has persistence and automation implications, and the pipeline schedule isn't running yet.

---

## Sources

**Budgeting authorities**
- CFPB, emergency fund guide: https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/
- CFPB, debt-to-income: https://www.consumerfinance.gov/ask-cfpb/what-is-a-debt-to-income-ratio-en-1791/
- CFPB, determine your down payment: https://www.consumerfinance.gov/owning-a-home/prepare/determine-your-down-payment/
- CFPB, automatic saving: https://www.consumerfinance.gov/about-us/blog/looking-easy-way-save-money-make-it-automatic/
- CFPB, Your Money Your Goals toolkit: https://www.consumerfinance.gov/consumer-tools/educator-tools/your-money-your-goals/toolkit/ and https://files.consumerfinance.gov/f/documents/cfpb_your-money-your-goals_financial-empowerment_toolkit.pdf
- CFPB, analyzing budgets (50/30/20): https://files.consumerfinance.gov/f/documents/cfpb_building_block_activities_analyzing-budgets_guide.pdf
- CFPB, "My spending rule to live by": https://files.consumerfinance.gov/f/201603_cfpb_rules-to-live-by_my-spending-rule-to-live-by.pdf
- CFPB, home-buying monthly payment worksheet: https://files.consumerfinance.gov/f/documents/cfpb_buying-a-house_monthly-payment_worksheet.pdf
- MyMoney.gov, Save and Invest: https://www.mymoney.gov/saveandinvest
- Fannie Mae, maintenance budget: https://yourhome.fanniemae.com/own/how-build-your-maintenance-and-repair-budget
- HUD PD&R: https://www.huduser.gov/portal/pdredge/pdr-edge-frm-asst-sec-072425.html and https://www.huduser.gov/portal/publications/trends_hsg_costs_85-2005.pdf

**YNAB**
- Where does my money go (the four rules): https://www.ynab.com/guide/where-does-my-money-go
- True expenses: https://www.ynab.com/blog/why-embracing-your-true-expenses-is-everything
- Age your money: https://www.ynab.com/blog/the-key-to-reducing-your-money-stress
- API OpenAPI spec: https://api.ynab.com/papi/open_api_spec.yaml
- Edit Plan: https://support.ynab.com/plan-and-adjust-with-edit-plan-and-cost-to-be-me-ByR7vpqPyx
- Export plan data: https://support.ynab.com/en_us/how-to-export-plan-data-Sy_CouWA9
- YNAB Together: https://support.ynab.com/en_us/ynab-together-B1nS78Cki

**Actual Budget**
- Budgeting: https://actualbudget.org/docs/budgeting/
- Categories: https://actualbudget.org/docs/budgeting/categories
- Tracking budget: https://actualbudget.org/docs/getting-started/tracking-budget
- Goal templates: https://github.com/actualbudget/docs/blob/master/docs/experimental/goal-templates.md
- Backup/export: https://github.com/actualbudget/docs/blob/master/docs/backup-restore/backup.md
- Subcategory issues and PR: https://github.com/actualbudget/actual/issues/1320, https://github.com/actualbudget/actual/issues/3320, https://github.com/actualbudget/actual/pull/5268

**Monarch**
- Flex budgeting: https://help.monarch.com/hc/en-us/articles/32125337244052-Understanding-Flex-Budgeting
- Flex budgeting blog: https://www.monarch.com/blog/fixed-flex-spending-what-it-is-and-how-to-get-started
- Rollovers: https://help.monarch.com/hc/en-us/articles/4411119762196-Rollover-budget-feature
- Group budgeting: https://help.monarch.com/hc/en-us/articles/18345219809940-Group-Budgeting
- Save-up goals: https://help.monarch.com/hc/en-us/articles/44373182867476-Using-Save-Up-Goals
- Growth rates in goals: https://help.monarch.com/hc/en-us/articles/47822256713236-Growth-Rates-in-Save-Up-Goals
- Forecasting: https://help.monarch.com/hc/en-us/articles/48344305092244-Forecasting-in-Monarch
- Budget calendar view: https://help.monarch.com/hc/en-us/articles/360051885292-Budget-Forecast

**Copilot Money**
- Rollovers: https://help.copilot.money/en/articles/3790828-budget-rollovers
- Category groups: https://help.copilot.money/en/articles/3767655-groups-of-categories
- Optional budgeting: https://help.copilot.money/en/articles/6282850-optional-budgeting
- Rebalancing: https://help.copilot.money/en/articles/6206302-rebalancing-your-budget
- Transaction export: https://help.copilot.money/en/articles/5944414-exporting-your-transaction-data

**Lunch Money**
- Budget setup: https://support.lunchmoney.app/guides/budgeting/step-2-setting-up-your-budget
- Transaction export: https://support.lunchmoney.app/finances/transactions/other-features
- Savings goals with rollovers: https://lunchmoney.app/blog/how-to-track-savings-goals-with-rollovers

**Firefly III**
- Budgets concept: https://github.com/firefly-iii/docs/blob/main/docs/docs/explanation/financial-concepts/budgets.md
- Managing budgets: https://github.com/firefly-iii/docs/blob/main/docs/docs/how-to/firefly-iii/finances/budgets.md
- Piggy banks: https://github.com/firefly-iii/docs/blob/main/docs/docs/explanation/financial-concepts/piggy-banks.md
- Exporting data: https://github.com/firefly-iii/docs/blob/main/docs/docs/tutorials/firefly-iii/exporting-data.md

**Plaid**
- Transactions API (personal_finance_category): https://plaid.com/docs/api/products/transactions/

**Export specs and libraries**
- RFC 4180: https://www.rfc-editor.org/rfc/rfc4180
- ECMA-376: https://ecma-international.org/publications-and-standards/standards/ecma-376/
- OWASP CSV injection: https://community.owasp.org/attacks/CSV_Injection
- Microsoft, opening UTF-8 CSV files in Excel: https://support.microsoft.com/de-de/office/ordnungsgem%C3%A4%C3%9Fes-%C3%B6ffnen-von-csv-utf-8-dateien-in-excel-8a935af5-3416-4edd-ba7e-3dfd2bc4a032 and https://learn.microsoft.com/en-us/answers/questions/5104482/how-to-open-csv-file-encoded-with-utf-8-with-excel
- XlsxWriter formulas: https://xlsxwriter.readthedocs.io/working_with_formulas.html
- openpyxl formulae: https://openpyxl.readthedocs.io/en/3.1/simple_formulae.html
- SheetJS: https://docs.sheetjs.com/docs/, https://docs.sheetjs.com/docs/csf/features/formulae, https://docs.sheetjs.com/docs/getting-started/installation/frameworks
- ExcelJS: https://github.com/exceljs/exceljs
- PyPI: https://pypi.org/project/XlsxWriter/ and https://pypi.org/project/openpyxl/
