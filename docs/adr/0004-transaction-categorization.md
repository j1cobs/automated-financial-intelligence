# ADR 0004: Transaction categorization — Plaid PFC + merchant memory

## Status

Accepted (2026-08-26). Complements ADR 0002 (transaction identity); live production phase.

## Context

Every transaction in the live database is stamped `category = 'Uncategorized'` or `'uncategorized'` — a consequence of `pipeline/runner.py:86-88` calling `build_placeholder_models()`, whose `PlaceholderTransactionClassifier` stamps a constant string on every row. The Budget tab, category charts in Overview and Cash Flow, and category-drift detection in the Home tab are all wired and working — they simply have nothing to show. Additionally, a live bug split the canonical category into two case variants (`'Uncategorized'` / `'uncategorized'`), with the lowercase version absent from the `categories` table altogether.

**Measurement taken at decision time (2026-08-26, live Postgres):**

| Measurement | Value | Consequence |
|---|---|---|
| Rows in `budgets` | **0** | Nothing downstream breaks if the taxonomy changes |
| Distinct `user_category` corrections | **0** | No manual work to preserve when switching taxonomies |
| Live `category` case variants | `'Uncategorized'` (754), `'uncategorized'` (62) | A case-inconsistency bug splitting one logical category into two separate strings in the UI; the lowercase one isn't in the canonical `categories` table at all |

The zero budgets and zero corrections finding is what makes this the cheapest possible moment to change the taxonomy wholesale. It also eliminates the main argument against adopting Plaid's personal-finance-category (PFC) taxonomy as-is.

**Why not a BERT model.** Two HuggingFace transaction-categorization models were investigated and rejected on evidence:

- `fahadkamraan/transaction-categorizer` (DistilBERT, 268 MB, 17 labels, trained on US-bank-transaction-categories-v2): Reported 99.88% accuracy is a red flag; real transaction categorization does not reach that, and exact-string dedup does not catch `METRO #4521` vs. `METRO #7832` as variants. The model's own card warns it "may generalise poorly to non-English or very different regional bank formats." 14 monthly downloads.
- `kuro-08/bert-transaction-categorization` (BERT-base, 438 MB, 25 labels): Consumer-lifestyle taxonomy (`Festivals`, `Grooming`, `Social Life`, `Culture`) with no `Income`, no `Fees`, no `Insurance`. No disclosed metrics, no license, no published training set.

Both are English-only. This household's accounts are Desjardins and BNC in Quebec, where merchant strings read `HYDRO-QUEBEC`, `COUCHE-TARD`, `PROVIGO`, `METRO`, `LE GERMAIN CHARLEVOIX BAIE`. A US-English-trained transformer has never seen those tokens. Adding `torch` + `transformers` (~800 MB of wheels, 2–3 min/run) to a daily cron to run a model trained on a distribution excluding this user's data is a bad trade.

More fundamentally: **for a single household, the merchant name is the label.** `METRO → FOOD_AND_DRINK` is a lookup, not an inference. A transformer's value is generalizing to unseen merchants, but this dataset has ~150 distinct merchants where the top ~30 dominate the volume and repeat monthly. Merchant memory (user corrections, remembered and applied to the same merchant going forward) is a better fit.

## Decision

**Three-layer cascade: merchant memory → Plaid's personal_finance_category primary → UNCATEGORIZED fallback.**

| Question | Decision |
|---|---|
| Taxonomy | **Adopt Plaid's PFC primary wholesale** — 17 distinct values observed with 100% coverage across all configured tokens; no ambiguity about what to seed |
| Cascade layers | **Merchant memory (user corrections) → Plaid PFC primary → UNCATEGORIZED fallback** |
| Layer 3 (TF-IDF) | **Deferred** — the probe showed no coverage gap large enough to justify it yet; build it when evidence emerges that the cascade is insufficient |
| Storage format | **Raw `SCREAMING_SNAKE_CASE`** (e.g. `FOOD_AND_DRINK`, `UNCATEGORIZED`); formatting for display belongs in the UI (frontend), matching this repo's existing rule that `savings_rate` is stored as a fraction, not a percentage |
| Non-Plaid sources | Fall through the cascade to `UNCATEGORIZED` — seed data and future CSV/manual-entry sources have no PFC value to read |
| User corrections | Remembered by merchant, not per-row — one correction applies going forward to every transaction from that merchant, with exact-match backfill for rows already stored. Deliberate limitation: backfill on raw merchant_name/description (no spelling normalization across historical rows); cross-spelling convergence only happens going forward when the cascade recomputes merchant_key at pipeline-run time |

## Consequences

- **Cascade precedence and debuggability.** `category` and a new `category_source` column record which layer assigned the value. `category_source` is one of: `'merchant'` (merchant memory), `'plaid'` (Plaid's PFC primary), `'user'` (reserved for potential direct per-row corrections, not used this phase), or `'none'` (fallback, category is `UNCATEGORIZED`). This makes the cascade auditable and is where a future layer-3 (TF-IDF) decision gets measured against — did it add value beyond the cascade?
- **Merchant memory is atomic and scoped.** `merchant_categories` (migration 022) stores one row per distinct normalized merchant key, with the category and source. A single user correction via the API updates one transaction's `user_category`, upserts the merchant memory entry, and backfills `user_category` on every other unmodified row from the same merchant (exact-string match). This two-part flow (immediate backfill + ongoing cascade at pipeline time) means the user sees the correction reflected immediately in the UI, but future transactions from the same merchant are guaranteed to pick it up even if Plaid later sends a spelling variant that doesn't exact-match any stored row.
- **Merchant key normalization is deliberate and under-merging-biased.** The `merchant_key()` normalizer (analytics/categorizer.py) strips leading `Purchase /` prefix, trailing city/province codes (one word + 2-letter code), and trailing store numbers, after uppercasing. This targets clear noise patterns specific to Plaid/bank data and is unit-tested. Under-merging (two keys for one merchant) costs one extra user correction; over-merging (one key for two different merchants) silently corrupts a category. The bias is explicit in the code and the reason `Cafe Du Parquet` appearing under three spellings in the probe (`Cafe Du Parquet`, `CAFE DU PARQUET MONTREAL QC`, `Purchase /CAFE DU PARQUET`) maps to one key.
- **Exact-match backfill is a same-run convenience, not a substitute for cascade-time normalization.** When `update_transaction_category()` backfills, it matches on raw `COALESCE(merchant_name, description)` because `merchant_key` is computed at read/cascade time, not stored in `transactions`. Cross-spelling historical backfill only happens going forward when the cascade recomputes merchant_key from merchant_name/description at pipeline-run time and looks it up in merchant_categories. This is a deliberate limitation (not a bug) — reimplementing the normalizer in SQL would split the source of truth. The tradeoff is documented and acceptable: if a user corrects `CAFE DU PARQUET MONTREAL QC` today, `Cafe Du Parquet` rows from six months ago won't retroactively pick up the correction (they already have a `user_category` set by one of the immediate backfill passes), and rows with *different* raw spellings won't either until a future pipeline run recomputes the key. Real merchants do repeat daily, so this converges fast in practice.
- **Storage: five new columns on `transactions`, three new columns for merchant memory.** Migrations 021 (PFC fields + category_source), 022 (merchant_categories table), 023 (case-bug fix + taxonomy seed) add:
  - `pfc_primary`, `pfc_detailed`, `pfc_confidence` (Plaid's PFC attributes, nullable, round-trip through ingestion/upsert)
  - `merchant_name` (Plaid-cleaned merchant name, nullable, same retention rules)
  - `category_source` (which cascade layer won, one of 'plaid'/'merchant'/'user'/'none')
  - `merchant_categories(merchant_key TEXT PRIMARY KEY, category TEXT NOT NULL, source TEXT DEFAULT 'user', updated_at TIMESTAMPTZ DEFAULT NOW())`
- **Ingestion carries four new normalized fields.** `PlaidIngestor._normalize()` extracts `merchant_name` and the three PFC fields straight from the raw Plaid transaction dict, following the existing NULL-means-unknown rule (no coercion to defaults).
- **Pipeline wiring: whole-frame call to cascade, mode-gated via `build_models()`.** The classification block in `pipeline/runner.py` now calls `build_models(settings.categorizer_mode)`, which gates between `"cascade"` (default, `CascadeCategorizer` + placeholder outlier detector) and `"placeholder"` (unchanged pre-Phase-18 behavior, for backward compatibility and tests). In cascade mode, the runner passes the full transaction frame to `cascade.categorize(frame, merchant_lookup)` rather than just the description Series — the cascade needs `pfc_primary`, `merchant_name`, and the computed merchant_key. Outlier detection remains unchanged (placeholder only this phase).

## Alternatives considered

- **Two BERT models (rejected, with evidence).** Both failed on real data: US-English-only training, wrong taxonomy (no Income/Fees/Insurance), and unverifiable metrics. The training distribution excludes Quebec merchant names entirely.
- **Plaid's DETAILED category level as primary (rejected).** Plaid returns ~104 categories at the detailed level, too granular for household budgeting (`Festivals`, `Grooming`, `ATM Withdrawal`). The DETAILED values are stored anyway (migration 021, `pfc_detailed` column) for future drill-down UX or training signal; DETAILED is not wired to the cascade or the UI yet.
- **Layer 3 (TF-IDF) built now, pending evidence (rejected).** The probe showed 100% PFC coverage with only 67% LOW confidence — plenty of room for the cascade to converge via merchant memory before spending complexity on layer 3. Build it when evidence emerges that layer 2 is insufficient (e.g., merchant memory hits a ceiling or users stop making corrections).
- **Per-row `user_category` corrections without merchant memory (rejected).** One user edit on one `COUCHE-TARD` row would not carry forward to the next pipeline run, forcing the same correction repeatedly on similar rows. Merchant memory (layer 2 remembering the choice, layer 1 applying it at cascade time) is what makes a single correction useful.
- **Overwrite Plaid PFC if it's LOW confidence (rejected).** The probe found 67% of rows at LOW confidence, but that is Plaid's honest assessment, not a sign the value is wrong. Backfilling layer 3 to replace LOWs would require training signal (labeled data); the decision to defer layer 3 means trusting Plaid's best guess when the user hasn't corrected it yet.

## Verification

1. **Probe passes (gate).** The probe measured 100% PFC coverage, 17 distinct primary values, and identified Café du Parquet as a concrete merchant_key bug (three spellings), confirming that normalization is needed.
2. **Probe result seeds migration 023.** The exact 17 categories observed (FOOD_AND_DRINK, GENERAL_MERCHANDISE, INCOME, etc.) are what migration 023 inserts; "what we saw" and "Plaid's official taxonomy" are the same list.
3. `merchant_key()` test coverage: four spellings of one merchant (`Cafe Du Parquet`, `CAFE DU PARQUET MONTREAL QC`, `Purchase /CAFE DU PARQUET`, plus a store-numbered variant) collapse to one key; two actually-different merchants never collide.
4. Cascade precedence: merchant memory beats Plaid PFC beats UNCATEGORIZED. An inserted merchant_categories entry is picked up on the next row classified.
5. Backfill never overwrites: one user correction on `COUCHE-TARD`, then a different one on a different `COUCHE-TARD` row, then both survive.
6. Pipeline re-run safety: `user_category`, `is_recurring`, `is_duplicate` survive upsert unchanged (because `upsert_transactions` never lists them in the INSERT).
7. Category PATCH endpoint returns `CategoryUpdateResponse(backfilled_count)` — backfilled_count > 0 is visible in the UI and confirms the user the correction is broadcast.
8. `web` checks: `npm run test && npx tsc -b && npm run lint && npm run format:check` all pass; `formatCategory()` renders `FOOD_AND_DRINK` as `Food and Drink`.
9. Scratch-DB run: `python main.py` against an empty database populates `category_source` overwhelmingly with `'plaid'`, a handful with `'none'` (seed data), zero `'Uncategorized'`/`'uncategorized'` case duplicates.
10. Production run: Budget tab lists real categories; category charts have more than one slice; ledger dropdown shows the Plaid taxonomy formatted for display; a category correction on one row propagates to others from the same merchant within the same run.
11. End-to-end correction loop: set category on one `COUCHE-TARD` row, all other `COUCHE-TARD` rows follow, backfill count > 0 surfaces in the UI, next pipeline run preserves `user_category` on all of them.
