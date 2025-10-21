# YSocial Database Schemas

This directory contains the database schema definitions for the YSocial application.

## Files

### Dashboard Database Schemas

- **`database_dashboard.db`** - SQLite database schema and data for dashboard/admin interface
- **`postgre_dashboard.sql`** - PostgreSQL equivalent schema for dashboard database

### Server Database Schemas

- **`database_clean_server.db`** - SQLite schema for experiment/simulation server
- **`postgre_server.sql`** - PostgreSQL equivalent schema for server database

### Configuration Files

- **`prompts.json`** - LLM prompts for agent behaviors
- **`prompts_forum.json`** - LLM prompts for forum-style interactions

## Schema Consistency

Both SQLite and PostgreSQL variants are maintained in parallel and kept synchronized:

- ✅ Same table structures
- ✅ Same field definitions (with appropriate type mappings)
- ✅ Same relationships and constraints
- ✅ Syntax differences only where necessary (AUTOINCREMENT vs SERIAL, etc.)

## Dashboard Database Tables (29 tables)

### Core Management
- `admin_users` - Dashboard user accounts and authentication
- `exps` - Experiment configurations
- `exp_stats` - Experiment statistics and metrics
- `client` - Simulation client configurations
- `client_execution` - Client execution state tracking

### Agent & Population Management
- `agents` - AI agent profiles and configurations
- `agent_profile` - Extended agent profile information
- `agent_population` - Agent-to-population associations
- `population` - Population group definitions
- `population_experiment` - Population-to-experiment associations
- `population_activity_profile` - Activity profile distributions

### Content Sources
- `pages` - News organizations and content pages
- `page_population` - Page-to-population associations
- `page_topic` - Page-to-topic associations

### Configuration Tables
- `content_recsys` - Content recommendation algorithms
- `follow_recsys` - Follower recommendation algorithms
- `education` - Education level options
- `languages` - Available language options
- `leanings` - Political leaning options
- `nationalities` - Nationality options
- `toxicity_levels` - Toxicity level classifications
- `age_classes` - Age group classifications
- `professions` - Professional occupation definitions

### Topics & Organization
- `topic_list` - Available topic categories
- `exp_topic` - Experiment-to-topic associations
- `user_experiment` - User-to-experiment associations

### Activity & Execution
- `activity_profiles` - Hourly activity patterns
- `ollama_pull` - LLM model download tracking
- `jupyter_instances` - JupyterLab instance management

## Field Usage Analysis

A comprehensive analysis of all database fields was conducted on October 21, 2025:

**Results:**
- ✅ All fields are actively used (0 unused fields found)
- ✅ Schemas are consistent between SQLite and PostgreSQL
- ✅ Database is well-maintained with no cleanup needed

**See reports:**
- `../DATABASE_FIELD_ANALYSIS_REPORT.md` - Detailed technical report
- `../DATABASE_CLEANUP_ANALYSIS.md` - Developer summary
- `../DATABASE_ANALYSIS_EXECUTIVE_SUMMARY.md` - Executive overview

## Usage

### SQLite (Development/Testing)

```bash
# Connect to dashboard database
sqlite3 data_schema/database_dashboard.db

# View schema
.schema

# List tables
.tables
```

### PostgreSQL (Production)

```bash
# Create database from schema
psql -U postgres -d ysocial -f data_schema/postgre_dashboard.sql

# Connect to database
psql -U postgres -d ysocial
```

## Maintenance

### Adding New Fields

When adding new database fields:

1. Update both SQLite and PostgreSQL schemas
2. Update `y_web/models.py` with corresponding SQLAlchemy model
3. Verify field is actually needed (not speculative)
4. Document field purpose in code comments
5. Run tests to verify schema changes
6. Update this README if adding new tables

### Schema Synchronization

Always maintain consistency between:
- SQLite schema (`database_dashboard.db`)
- PostgreSQL schema (`postgre_dashboard.sql`)
- ORM models (`y_web/models.py`)

## Database Type Mappings

| SQLite Type | PostgreSQL Type | Notes |
|------------|-----------------|-------|
| INTEGER | INTEGER / SERIAL | SERIAL for auto-increment |
| TEXT | TEXT / VARCHAR | VARCHAR when length limits needed |
| REAL | REAL | Floating point numbers |
| INTEGER (bool) | BOOLEAN | SQLite uses 0/1, PostgreSQL has native BOOLEAN |

## Notes

- All schemas include proper foreign key constraints
- Cascading deletes are configured where appropriate
- Default values are specified for optional fields
- Indexes should be added as needed for performance

## Questions?

For questions about specific tables or fields:
1. Check the model definitions in `y_web/models.py`
2. Review the analysis reports in the parent directory
3. Examine the schema files directly in this directory

---

**Last Updated:** 2025-10-21  
**Schema Version:** Current with codebase  
**Status:** ✅ Maintained and Documented
