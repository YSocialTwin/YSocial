-- Migration: Add recsys fields to Client model
-- Description: This migration adds crecsys and frecsys columns to the client table
--              to support recommendation system configuration at the client level
--              instead of at the population or agent level.
-- Date: 2025-10-27

-- For SQLite
ALTER TABLE client ADD COLUMN crecsys VARCHAR(50);
ALTER TABLE client ADD COLUMN frecsys VARCHAR(50);

-- For PostgreSQL (if using PostgreSQL instead of SQLite)
-- ALTER TABLE client ADD COLUMN IF NOT EXISTS crecsys VARCHAR(50);
-- ALTER TABLE client ADD COLUMN IF NOT EXISTS frecsys VARCHAR(50);
