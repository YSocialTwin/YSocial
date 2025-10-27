# Database Migrations

This directory contains SQL migration scripts for updating existing databases.

## How to Apply Migrations

### For SQLite Databases

1. Locate your database file (usually in `y_web/experiments/` directory)
2. Apply the migration using sqlite3:
   ```bash
   sqlite3 path/to/your/database.db < migrations/add_recsys_to_client.sql
   ```

### For PostgreSQL Databases

1. Connect to your database
2. Apply the migration:
   ```bash
   psql -d your_database_name -f migrations/add_recsys_to_client.sql
   ```

## Migration History

- **add_recsys_to_client.sql** (2025-10-27): Adds `crecsys` and `frecsys` columns to the `client` table to support recommendation system configuration at the client level instead of population/agent level.

## Notes

- If you're creating a new database from scratch, these migrations are not needed as SQLAlchemy will create the tables with all current columns automatically using `db.create_all()`.
- Only apply migrations to existing databases that were created before the schema changes.
- Always backup your database before applying migrations!
