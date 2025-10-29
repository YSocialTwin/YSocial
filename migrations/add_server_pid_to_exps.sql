-- Migration: Add server_pid column to exps table
-- Date: 2025-10-29
-- Description: Adds server_pid column to track server process IDs for graceful termination

-- For SQLite
-- ALTER TABLE exps ADD COLUMN server_pid INTEGER DEFAULT NULL;

-- For PostgreSQL
ALTER TABLE exps ADD COLUMN IF NOT EXISTS server_pid INTEGER DEFAULT NULL;
