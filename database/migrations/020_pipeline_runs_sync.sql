-- Records the /transactions/sync outcome of a pipeline run: how many rows Plaid's `removed`
-- (plus superseded pending lineage) caused to be deleted, and whether reconcile_transactions
-- ran (only ever true on a full_refresh sync -- see database/db.py::reconcile_transactions).
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS removed_count INTEGER;
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS full_refresh BOOLEAN;
