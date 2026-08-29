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
    merchant memory) and whose `.outlier_detector` is the same `PlaceholderOutlierDetector`
    used by the placeholder bundle, unchanged — outlier detection is out of scope for this
    phase. `"placeholder"` returns `build_placeholder_models()` unchanged, for tests/back-compat.

    Wiring `core/config.py` / `pipeline/runner.py` to call this is a later wave; this function
    is not yet called from production code.
    """
    if mode == "cascade":
        return PlaceholderModelBundle(
            classifier=CascadeCategorizer(),
            outlier_detector=PlaceholderOutlierDetector(),
        )
    if mode == "placeholder":
        return build_placeholder_models()
    raise ValueError(f"Unrecognized categorizer mode: {mode!r}")
