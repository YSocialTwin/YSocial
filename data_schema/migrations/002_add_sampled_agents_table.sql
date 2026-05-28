-- Migration: Add opinion_evolution_sampled_agents table for stable agent sampling
-- Date: 2026-01-21
-- Purpose: Store sampled agent IDs to maintain stable visualization across animation frames

CREATE TABLE IF NOT EXISTS opinion_evolution_sampled_agents (
    id                   SERIAL PRIMARY KEY,
    exp_id               INTEGER NOT NULL,
    topic_id             VARCHAR(50),  -- NULL for all topics, VARCHAR to support UUID in HPC experiments
    sample_percentage    INTEGER NOT NULL,
    sampled_agent_ids    TEXT NOT NULL,  -- JSON array of agent IDs
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraint
    CONSTRAINT fk_sampled_agents_exp FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
);

-- Create composite index for fast lookups
CREATE INDEX IF NOT EXISTS idx_sampled_agents_lookup ON opinion_evolution_sampled_agents(exp_id, topic_id, sample_percentage);

-- Create index on created_at for cache cleanup queries
CREATE INDEX IF NOT EXISTS idx_sampled_agents_created ON opinion_evolution_sampled_agents(created_at);

-- Add comment for documentation
COMMENT ON TABLE opinion_evolution_sampled_agents IS 'Stores sampled agent IDs for stable opinion evolution visualization. Agents are sampled once per (experiment, topic, percentage) combination and reused across all animation frames for stability and performance. Supports both integer topic IDs (standard) and UUID topic IDs (HPC experiments).';
