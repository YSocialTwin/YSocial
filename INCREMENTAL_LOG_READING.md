# Incremental Log Reading Implementation

## Overview

This document describes the incremental log reading implementation that optimizes plot generation in the `admin/experiment_details` page by avoiding repeated full scans of growing log files.

## Problem Statement

Previously, the system read entire log files (`_server.log` and `{client_name}_client.log`) every time plots needed to be refreshed. As experiments run longer, these log files grow, making full scans increasingly time-consuming.

## Solution

The solution implements:
1. **Database-backed metrics** - Pre-aggregated metrics stored in database tables
2. **Incremental reading** - Track file offsets to read only new log entries
3. **Automatic updates** - Endpoints update metrics before serving data

## Database Schema

### Tables Created

#### `log_file_offsets`
Tracks the last read position in each log file.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER/SERIAL | Primary key |
| exp_id | INTEGER | Experiment ID (FK to exps) |
| log_file_type | VARCHAR(50) | 'server' or 'client' |
| client_id | INTEGER | Client ID (NULL for server logs) |
| file_path | VARCHAR(500) | Relative path to log file |
| last_offset | BIGINT | Byte offset of last read position |
| last_updated | TIMESTAMP | Last update timestamp |

#### `server_log_metrics`
Aggregated metrics from server logs.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER/SERIAL | Primary key |
| exp_id | INTEGER | Experiment ID (FK to exps) |
| aggregation_level | VARCHAR(10) | 'daily' or 'hourly' |
| day | INTEGER | Simulation day |
| hour | INTEGER | Simulation hour (NULL for daily) |
| path | VARCHAR(200) | API endpoint path |
| call_count | INTEGER | Number of calls |
| total_duration | FLOAT | Sum of all durations |
| min_time | TIMESTAMP | Earliest timestamp |
| max_time | TIMESTAMP | Latest timestamp |

#### `client_log_metrics`
Aggregated metrics from client logs.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER/SERIAL | Primary key |
| exp_id | INTEGER | Experiment ID (FK to exps) |
| client_id | INTEGER | Client ID (FK to client) |
| aggregation_level | VARCHAR(10) | 'daily' or 'hourly' |
| day | INTEGER | Simulation day |
| hour | INTEGER | Simulation hour (NULL for daily) |
| method_name | VARCHAR(200) | Client method name |
| call_count | INTEGER | Number of calls |
| total_execution_time | FLOAT | Sum of execution times |

## How It Works

### 1. First Read (Cold Start)

When an endpoint is called for the first time:

1. No offset exists → start reading from byte 0
2. Parse all log entries and aggregate metrics
3. Store metrics in database tables
4. Record final byte offset for next read

### 2. Subsequent Reads (Incremental)

When an endpoint is called again:

1. Retrieve last offset from `log_file_offsets`
2. Seek to that position in the log file
3. Read only new entries since last position
4. Update aggregated metrics in database
5. Update offset to new position

### 3. Data Retrieval

When plots need data:

1. Endpoint calls update function (incremental read)
2. Query aggregated metrics from database
3. Return pre-computed aggregations as JSON

## API Endpoints

### `/admin/experiment_logs/<exp_id>`

Returns call volume and mean duration for each API path.

**Before**: Read entire `_server.log` on every request
**After**: Read only new entries, query database for aggregates

### `/admin/experiment_trends/<exp_id>`

Returns daily/hourly compute time and simulation time trends.

**Before**: Read entire `_server.log` and all client logs
**After**: Read only new entries from each log, query database

### `/admin/client_logs/<client_id>`

Returns call volume and execution time for each method.

**Before**: Read entire `{client_name}_client.log`
**After**: Read only new entries, query database

## Migration

### For Existing Installations

Run the migration script to add new tables:

```bash
python y_web/migrations/add_log_metrics_tables.py
```

This script:
- Creates tables in SQLite (default database)
- Optionally creates tables in PostgreSQL (if configured)
- Handles existing tables gracefully
- Is idempotent (safe to run multiple times)

### For New Installations

The schema is automatically included in:
- `data_schema/postgre_dashboard.sql` (PostgreSQL)
- Created by models in `y_web/models.py` (both databases)

## Performance Benefits

### Before
- **Time Complexity**: O(n) where n = total log entries
- **I/O**: Full file scan on every request
- **Memory**: All entries processed in memory

### After
- **Time Complexity**: O(m) where m = new entries since last read
- **I/O**: Partial file read (seek + read new entries)
- **Memory**: Only new entries processed

### Example Improvement

For a log file with 100,000 entries:
- **First read**: Process 100,000 entries → store in DB
- **Second read** (100 new entries): Process 100 entries only
- **Speedup**: ~1000x faster on subsequent reads

## Code Structure

```
y_web/
├── models.py                          # Database models
├── utils/
│   └── log_metrics.py                 # Incremental reading logic
├── routes_admin/
│   └── experiments_routes.py          # Updated endpoints
├── migrations/
│   └── add_log_metrics_tables.py      # Migration script
└── tests/
    └── test_incremental_log_reading.py # Tests
```

## Testing

Run tests with:

```bash
python -m pytest y_web/tests/test_incremental_log_reading.py -v
```

Tests cover:
- Offset tracking functionality
- Incremental parsing of server logs
- Incremental parsing of client logs
- Only new entries are read
- Invalid JSON handling

## Cleanup

When an experiment is deleted:

```python
# Explicit deletion in delete_simulation()
db.session.query(LogFileOffset).filter_by(exp_id=exp_id).delete()
db.session.query(ServerLogMetrics).filter_by(exp_id=exp_id).delete()
db.session.query(ClientLogMetrics).filter_by(exp_id=exp_id).delete()
```

This prevents orphaned data in the database.

## Future Enhancements

Potential improvements:
1. **Background processing** - Update metrics via scheduled tasks
2. **Batch updates** - Process multiple log files in parallel
3. **Compression** - Archive old metrics to reduce DB size
4. **Real-time updates** - WebSocket-based live plot updates
5. **Configurable aggregations** - User-defined time windows

## Troubleshooting

### Metrics not updating

Check:
1. Log file exists and is readable
2. Log file has valid JSON entries
3. Database tables exist (run migration if needed)
4. No errors in application logs

### Performance still slow

Possible causes:
1. Database indexes missing (check schema)
2. Large number of unique paths/methods
3. Database on slow storage
4. Consider batch processing if real-time not needed

### Database errors

Ensure:
1. Foreign key constraints are enabled (SQLite)
2. Tables have proper CASCADE DELETE
3. Indexes are created
4. Database has sufficient space

## References

- Models: `y_web/models.py`
- Utility functions: `y_web/utils/log_metrics.py`
- Endpoints: `y_web/routes_admin/experiments_routes.py`
- Migration: `y_web/migrations/add_log_metrics_tables.py`
- Tests: `y_web/tests/test_incremental_log_reading.py`
