-- Migration: Add latest_opinions_state column for incremental caching
-- Date: 2026-01-21
-- Purpose: Add support for incremental computation to opinion_evolution_cache table

-- Add the latest_opinions_state column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'opinion_evolution_cache' 
        AND column_name = 'latest_opinions_state'
    ) THEN
        ALTER TABLE opinion_evolution_cache 
        ADD COLUMN latest_opinions_state TEXT;
        
        COMMENT ON COLUMN opinion_evolution_cache.latest_opinions_state IS 'JSON state for incremental computation: {agent_id: {topic_id: {"opinion": float, "day": int, "hour": int}}}';
    END IF;
END $$;

-- Update table comment
COMMENT ON TABLE opinion_evolution_cache IS 'Caches pre-computed statistics for opinion evolution visualization to optimize animation performance. Supports incremental computation by storing latest_opinions state. Cache entries persist indefinitely.';
