-- Add user-taggable recurring flag; pipeline never writes this column
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN NOT NULL DEFAULT FALSE;
