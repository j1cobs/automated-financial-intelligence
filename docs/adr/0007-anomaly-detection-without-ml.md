# ADR 0007: Anomaly detection without ML — explainable rules plus a feedback memory

## Status

Accepted (2026-09-24). Supersedes the outlier half of PLAN.md Phase 7 ("DEFERRED: ML activation"); the classifier half was already superseded by ADR 0004. Implemented as PLAN.md Phase 34.

## Context

`analytics/outlier_detector.py` was written in Phase 1 and never wired up. It grouped transactions by category and applied a z-score under 8 rows per group, an `IsolationForest(contamination=0.03, n_estimators=200)` above. `analytics/models.py::build_models()` returned `PlaceholderOutlierDetector` in both modes, so `pipeline/runner.py` stamped `outlier_score = 0.0` and `is_outlier = FALSE` on every row on every run. The columns, the index, the `/anomalies` endpoint and a Transactions-tab scatter chart were all built and working — against data that was uniformly zero.

The user asked for the anomaly detector to be "added" and for a recommendation on whether to use ML. Activating what was already written was the obvious move. It was rejected on three grounds.

**Its output cannot be explained.** The model produces a score. "This transaction has anomaly score 0.83" is not a statement anyone can act on: it does not say what is unusual, compared to what, or by how much. Every alert this dashboard shows has to survive the question "why are you telling me this?", and a forest of isolation depths has no answer.

**A fixed contamination rate guarantees false positives.** `contamination=0.03` is not a threshold on unusualness; it is an instruction to label 3% of the input as anomalous. In a month where nothing whatsoever went wrong, it still flags 3% of rows. A detector that cannot stay silent trains the user to ignore it, which is worse than having none.

**On personal finance it converges on the wrong rows.** The largest transactions in a household's history are rent, mortgage payments, tuition, and occasional big-ticket purchases. These are precisely the points an isolation forest separates first. The live database contains four separate real `IKEA $250.00` charges on one day (ADR 0002); this user's data is full of legitimate large spending. The model would flag it every month, forever, and be right about the statistics and useless about the finances.

The opposite framing — what would actually be worth an alert? — produces two specific questions, both answerable without a model:

- Is a category spending materially more than it usually does *at this point in the month*?
- Did a recurring charge's amount change?

## Decision

**Retire the Isolation Forest. Delete `analytics/outlier_detector.py` and its tests.** Replace it with two deterministic detectors in `analytics/anomalies.py`, each of which generates the sentence it is asserting.

**Category drift.** Compare the current month's spend-to-date against the median spend by the **same day of the month** in prior months, scored by **MAD** (median absolute deviation).

- *Why MAD rather than standard deviation.* One freak month inflates a standard deviation enough to hide a genuine overspend the month after. A median absolute deviation is unmoved by a single outlier, which is the whole situation this detector exists for. Pinned by `test_one_outlier_month_does_not_mask_the_next`.
- *Why same-day-of-month, and no projection to end-of-month.* The first draft of this design projected the partial month to EOM and compared totals. On day 2, one ordinary purchase extrapolates to roughly 15× the month, so the detector would fire at the start of every single month. Comparing "spent by day 9" against "usually spent by day 9" needs no extrapolation and answers the question the user actually has: am I ahead of my usual pace right now?
- Severity: ≥2.5 MAD medium, ≥4.0 MAD high. Below medium emits nothing at all.
- Underspending is never flagged. This is a budget-drift detector, not a change detector.

**Price creep.** Compare a recurring stream's latest amount against the median of its earlier occurrences, with a **dual percent-and-dollar threshold** (≥10% *and* ≥$3 for medium; ≥25% *and* ≥$15 for high).

- Either threshold alone misfires. 20% of a $2 charge is 40 cents; $4 on a $400 charge is 1%. Requiring both suppresses small-stream noise and large-stream rounding at once.
- A price going *down* is not an alert.

**A minimum of 3 complete months of history before anything is emitted.** `pipeline/runner.py::run_pipeline` defaults `days_back=90`, so thin history is the normal early state rather than an edge case. Every explanation states how many months back it.

**Learning lives in the feedback loop, not in a model.** `anomaly_feedback` records dismissals, keyed `(kind, subject, period)`. This mirrors ADR 0004's `merchant_categories`: a user-correction memory feeding a deterministic rule is where the adaptation belongs, and it is inspectable in a way model weights are not.

**Dismissal is period-scoped, not permanent.** An earlier draft of this design suppressed a dismissed subject in all future periods and called that "the learning". That was wrong. Dismissing September's Dining drift because of a birthday would then silence October's, and the detector goes quiet exactly as it becomes useful. A category dismissed twelve months running is itself information — that the budget is wrong, not that the alert is.

**Storage: a typed `anomalies` table, not the existing per-transaction columns.** Drift is per-category-per-month and creep is per-stream; a category overspending is not a property of any one transaction. `UNIQUE (kind, subject, period)` makes detection idempotent across pipeline runs — the same discipline `transaction_hash` provides for transactions. Re-detection updates `severity` and `explanation` in place but preserves `detected_at`, so the alert stays current as the month develops while still recording when it first tripped.

## Consequences

**The frozen Streamlit dashboard needs a compatibility shim.** `app/dashboard.py` reads `is_outlier`/`outlier_score` at `:339`, `:787` and `:1195-1209`, and CLAUDE.md forbids editing that module. If Phase 34 simply stopped writing those columns, its anomalies view would sit permanently empty. So the pipeline keeps writing `is_outlier`, pointing it at the transactions that actually drive a live anomaly (the top 3 contributors per drift, the latest row per creep stream). This is a shim, not a feature: `DatabaseClient.set_outlier_flags` says so, and nothing in the React app reads those columns.

**The Transactions-tab anomaly scatter is removed.** It plotted `outlier_score`, which nothing meaningful writes any more. Anomalies now surface on the Overview card (the tab opened first, so an alert is actually seen) and inline on the Budget row whose cap the drift concerns — next to the number they describe. About 120 lines of chart code went with it.

**`sklearn` is no longer used by the detection path.** It remains in `requirements.txt` for `analytics/classifier.py`, which is likewise unused but not in this ADR's scope.

**If genuine fraud detection is ever wanted, this is not it.** These two detectors answer "is my spending drifting?" and "did a bill go up?". "Did someone else make this charge?" is a different question needing per-transaction scoring, and would be a new decision, not a revival of this one.

## Alternatives considered

- **Wire up the Isolation Forest as written.** Rejected for the three reasons above.
- **Keep the model but raise the threshold.** Does not fix explainability, and `contamination` is a proportion, not a severity — raising it changes *how many* rows are flagged, not *how unusual* they must be.
- **Compute anomalies on read instead of storing them.** No schema churn and always current, but dismissals still need somewhere to live, and there would be no record of what was flagged when.
- **New-merchant alerts** ("first ever charge at this merchant above $X"). Simple and fraud-adjacent, deferred as out of scope rather than rejected.

## See also

- `analytics/anomalies.py` — the detectors.
- `database/migrations/029_anomalies.sql` — the tables and the period-scoped feedback key.
- `tests/test_anomalies.py` — MAD robustness, the no-early-month-false-positive case, dual thresholds, and the period-scoped dismissal rule.
- ADR 0004 — the same user-correction-memory pattern, applied to categorization.
