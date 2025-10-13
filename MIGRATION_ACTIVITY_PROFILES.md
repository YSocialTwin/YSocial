# Activity Profiles Database Migration

## Issue

If you're getting the error:

```
sqlite3.OperationalError: no such column: activity_profiles.id
```

This means your existing `activity_profiles` table needs to be updated to include the `id` column.

## Solution

We've provided a migration script to fix this issue automatically.

### For SQLite (default):

```bash
python migrate_activity_profiles.py
```

### For PostgreSQL:

```bash
python migrate_activity_profiles.py --db-type postgresql
```

## What the migration does

The migration script will:

1. Check if the `activity_profiles` table exists
2. Check if the `id` column is present
3. If the `id` column is missing:
   - Backup any existing activity profile data
   - Drop and recreate the table with the correct schema
   - Restore the backed-up data

## Manual Migration (Alternative)

If you prefer to migrate manually, follow these steps:

### SQLite:

```bash
sqlite3 y_web/db/dashboard.db << 'EOF'
-- Backup existing data
CREATE TABLE activity_profiles_backup AS SELECT * FROM activity_profiles;

-- Drop old table
DROP TABLE activity_profiles;

-- Create new table with id column
CREATE TABLE activity_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(120) NOT NULL UNIQUE,
    hours VARCHAR(100) NOT NULL
);

-- Restore data
INSERT INTO activity_profiles (name, hours)
SELECT name, hours FROM activity_profiles_backup;

-- Clean up
DROP TABLE activity_profiles_backup;
EOF
```

### PostgreSQL:

```bash
psql -U postgres -d dashboard << 'EOF'
-- Backup existing data
CREATE TABLE activity_profiles_backup AS SELECT * FROM activity_profiles;

-- Drop old table
DROP TABLE activity_profiles;

-- Create new table with id column
CREATE TABLE activity_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    hours VARCHAR(100) NOT NULL
);

-- Restore data
INSERT INTO activity_profiles (name, hours)
SELECT name, hours FROM activity_profiles_backup;

-- Clean up
DROP TABLE activity_profiles_backup;
EOF
```

## For New Installations

If you're installing YSocial for the first time after this update, the database schema files have already been updated and you don't need to run any migration. The correct table structure will be created automatically.

## Questions?

If you encounter any issues with the migration, please:

1. Backup your database before running the migration
2. Check that you have the necessary permissions to modify the database
3. Report the issue with the full error message
