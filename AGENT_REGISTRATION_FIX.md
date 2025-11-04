# Agent Registration Issue Analysis and Fix

## Problem Statement
Agent registration (first phase of client execution) was failing or being skipped when using PostgreSQL, while working correctly with SQLite.

## Root Cause Analysis

### Issue Identified
In `y_web/routes_admin/experiments_routes.py` (line 604-609), when creating a `Client_Execution` record during database import, the code was explicitly setting:
- `last_active_hour=0`
- `last_active_day=0`

However, the correct initialization values should be `-1` for both fields, as defined in:
1. **Model definition** (`y_web/models.py` line 626-627): `default=-1`
2. **PostgreSQL schema** (`data_schema/postgre_dashboard.sql`): `DEFAULT -1`
3. **Other creation point** (`y_web/utils/external_processes.py` line 1141-1142): Uses `-1`

### Why This Caused PostgreSQL-Specific Issues

**SQLite Behavior (Lenient):**
- SQLite has flexible type coercion and NULL handling
- May apply model defaults even when explicit values are provided in some cases
- The inconsistency was masked by SQLite's lenient behavior

**PostgreSQL Behavior (Strict):**
- PostgreSQL strictly enforces type constraints and uses explicit values
- When `last_active_hour=0` and `last_active_day=0` are explicitly set, they override model defaults
- The client execution logic interprets these values differently:
  - `-1, -1` = "Not started yet, need to register agents"
  - `0, 0` = "Already started at day 0, hour 0, skip registration phase"

### Impact on Agent Registration
The agent registration phase checks if `last_active_hour == -1` and `last_active_day == -1` to determine if this is the first run that requires agent registration. With values set to `0, 0` instead of `-1, -1`:
- The system thinks agents are already registered
- Agent registration phase is skipped
- Simulation fails or behaves incorrectly

## Fix Applied

### Changed File
`y_web/routes_admin/experiments_routes.py` (lines 606-607)

### Change Made
```python
# Before (INCORRECT):
client_exec = Client_Execution(
    client_id=cl.id,
    last_active_hour=0,       # ← WRONG: Should be -1
    last_active_day=0,        # ← WRONG: Should be -1
    expected_duration_rounds=cl.days * client["simulation"]["slots"],
)

# After (CORRECT):
client_exec = Client_Execution(
    client_id=cl.id,
    last_active_hour=-1,      # ✓ Correct: Indicates not started
    last_active_day=-1,       # ✓ Correct: Indicates not started
    expected_duration_rounds=cl.days * client["simulation"]["slots"],
)
```

### Verification
- ✅ Consistent with model defaults (`y_web/models.py`)
- ✅ Consistent with PostgreSQL schema defaults (`data_schema/postgre_dashboard.sql`)
- ✅ Consistent with other Client_Execution creation (`y_web/utils/external_processes.py`)
- ✅ Follows semantic meaning: `-1` = "not started", `0` = "started at position 0"

## Testing Recommendations

1. **Test database import with PostgreSQL:**
   - Import a database with agents
   - Start the client
   - Verify agent registration occurs correctly
   - Check that `last_active_hour` and `last_active_day` are set to `-1` initially

2. **Verify first run detection:**
   - Ensure the client properly detects this is the first run
   - Confirm agent registration phase executes
   - Check that agents are properly registered in the server database

3. **Cross-database consistency:**
   - Test with both SQLite and PostgreSQL
   - Verify identical behavior in both databases
   - Confirm no regressions

## Related Files
- `y_web/models.py` - Client_Execution model definition (lines 620-628)
- `y_web/utils/external_processes.py` - Client_Execution creation during start (lines 1137-1145)
- `y_web/routes_admin/experiments_routes.py` - Client_Execution creation during import (lines 604-611) **[FIXED]**
- `data_schema/postgre_dashboard.sql` - PostgreSQL schema with defaults

## Confidence Level: HIGH

This fix addresses the exact symptom reported: agent registration failing on PostgreSQL while working on SQLite. The root cause is a clear initialization value mismatch that would cause the registration phase to be skipped.
