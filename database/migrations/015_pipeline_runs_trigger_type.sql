-- Which GitHub Actions event produced this run: "schedule" (daily cron) or "workflow_dispatch"
-- (manual trigger), or "local" for a run started outside GitHub Actions. Lets two same-day rows
-- be told apart instead of looking like a duplicate-write bug.
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS trigger_type TEXT;
