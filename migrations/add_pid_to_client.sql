-- Migration: Add pid column to client table
-- Date: 2025-10-30
-- Description: Adds pid column to track client process IDs for graceful termination

-- For SQLite
-- ALTER TABLE client ADD COLUMN pid INTEGER DEFAULT NULL;

-- For PostgreSQL
ALTER TABLE client ADD COLUMN IF NOT EXISTS pid INTEGER DEFAULT NULL;
