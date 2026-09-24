from __future__ import annotations

from analytics.categorizer import CascadeCategorizer
from analytics.placeholders import (
    PlaceholderModelBundle,
    PlaceholderOutlierDetector,
    build_placeholder_models,
)

# Bundle shape parity with PlaceholderModelBundle is intentional: the pipeline wiring wave
# accesses `.classifier` / `.outlier_detector` by attribute name regardless of mode. A plain
# tuple or a new dataclass with different attribute names would force runner.py to branch on
# mode, defeating the point of the seam. Reusing PlaceholderModelBundle's dataclass directly
# means CascadeCategorizer just needs to satisfy the same attribute contract, which it does:
# `.categorize(transactions, merchant_lookup)` replaces `.categorize(descriptions)` — the
# runner's classification block is expected (per PLAN.md Step 3) to change from operating on
# `transactions["description"]` to the whole frame, since the cascade needs `pfc_primary` and
# `merchant_name`. That whole-frame call shape is chosen deliberately over a
# backward-compatible Series-only signature, which cannot carry the columns the cascade needs.


def build_models(mode: str) -> PlaceholderModelBundle:
    """Select the categorization model bundle for `mode`.

    `"cascade"` returns a bundle whose `.classifier` is a `CascadeCategorizer` (Plaid PFC +
    merchant memory). `"placeholder"` returns `build_placeholder_models()` unchanged, for
    tests/back-compat.

    `.outlier_detector` is `PlaceholderOutlierDetector` in **both** modes, and permanently so.
    Phase 34 retired `analytics/outlier_detector.py` (an Isolation Forest, written in Phase 1
    and never wired up) rather than activating it: its score cannot be explained, and a fixed
    `contamination=0.03` flags ~3% of rows however ordinary the month was. Real anomaly
    detection now lives in `analytics/anomalies.py` and writes its own table; the placeholder
    survives only to zero the legacy `outlier_score`/`is_outlier` columns each run, which the
    frozen Streamlit dashboard still reads. See docs/adr/0007-anomaly-detection-without-ml.md.
    """
    if mode == "cascade":
        return PlaceholderModelBundle(
            classifier=CascadeCategorizer(),
            outlier_detector=PlaceholderOutlierDetector(),
        )
    if mode == "placeholder":
        return build_placeholder_models()
    raise ValueError(f"Unrecognized categorizer mode: {mode!r}")
