-- Migration: Add opinion_evolution_cache table for performance optimization
-- Date: 2026-01-21
-- Purpose: Cache pre-computed statistics for opinion evolution animation to improve performance
--          Supports incremental computation by storing latest_opinions state

CREATE TABLE IF NOT EXISTS opinion_evolution_cache (
    id                   SERIAL PRIMARY KEY,
    exp_id               INTEGER NOT NULL,
    day                  INTEGER NOT NULL,
    hour                 INTEGER NOT NULL,
    topic_id             INTEGER,  -- NULL for all topics
    total_opinions       INTEGER NOT NULL,
    social_interactions  INTEGER NOT NULL,
    unique_agents        INTEGER NOT NULL,
    binned_data          TEXT NOT NULL,  -- JSON string: {group_name: count}
    latest_opinions_state TEXT,  -- JSON string: state for incremental computation
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraint
    CONSTRAINT fk_opinion_cache_exp FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
);

-- Create composite index for fast lookups during animation
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON opinion_evolution_cache(exp_id, day, hour, topic_id);

-- Create index on created_at for cache cleanup queries
CREATE INDEX IF NOT EXISTS idx_cache_created ON opinion_evolution_cache(created_at);

-- Add comment for documentation
COMMENT ON TABLE opinion_evolution_cache IS 'Caches pre-computed statistics for opinion evolution visualization to optimize animation performance. Supports incremental computation by storing latest_opinions state. Cache entries persist indefinitely.';
