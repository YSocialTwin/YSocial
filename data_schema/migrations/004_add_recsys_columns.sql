-- Migration: Add category and enabled columns to content_recsys and follow_recsys tables
-- Date: 2026-02-05
-- Purpose: Add support for categorization and client-specific enablement of recommendation systems
--          The enabled column contains a comma-separated list of clients that support the recommender
--          (e.g., "HPC,Standard" if both support it, otherwise only "HPC" or "Standard")

-- Add columns to content_recsys table
ALTER TABLE content_recsys ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE content_recsys ADD COLUMN IF NOT EXISTS enabled TEXT;

-- Add columns to follow_recsys table
ALTER TABLE follow_recsys ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE follow_recsys ADD COLUMN IF NOT EXISTS enabled TEXT;

-- Update existing records to have "HPC,Standard" in enabled column
UPDATE content_recsys SET enabled = 'HPC,Standard' WHERE enabled IS NULL;
UPDATE follow_recsys SET enabled = 'HPC,Standard' WHERE enabled IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN content_recsys.category IS 'Optional categorization for recommendation systems';
COMMENT ON COLUMN content_recsys.enabled IS 'Comma-separated list of clients supporting this recommender (e.g., HPC,Standard)';
COMMENT ON COLUMN follow_recsys.category IS 'Optional categorization for recommendation systems';
COMMENT ON COLUMN follow_recsys.enabled IS 'Comma-separated list of clients supporting this recommender (e.g., HPC,Standard)';
