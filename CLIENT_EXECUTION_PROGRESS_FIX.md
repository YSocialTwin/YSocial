# Client Execution Progress Fix

## Problem
Client progression bars in `/admin/run_client` and `/admin/dashboard` were not updating properly when using PostgreSQL. They worked correctly with SQLite.

## Root Cause Analysis

### Symptoms
- Progress bars remained at 0% or didn't update during client execution
- `last_active_hour` and `last_active_day` fields in Client_Execution table weren't being updated
- Issue only occurred with PostgreSQL, not SQLite

### Root Cause
In `y_web/utils/external_processes.py` (lines 1333-1337), the Client_Execution record was being updated during each simulation iteration:

```python
# Original code:
ce = Client_Execution.query.filter_by(client_id=cli_id).first()
ce.elapsed_time += 1
ce.last_active_hour = h
ce.last_active_day = d
db.session.commit()
```

**The Problem:**
- The object `ce` was queried and its attributes were modified
- However, the modified object was NOT explicitly added back to the session
- SQLAlchemy's session change tracking behaves differently between databases
- **SQLite**: More lenient, automatically tracks in-memory changes
- **PostgreSQL**: Stricter transaction handling, requires explicit marking of modified objects

### Why It Worked on SQLite
SQLite's lenient transaction handling and SQLAlchemy's behavior with SQLite connections automatically tracked the in-memory changes to the object, even without explicitly calling `db.session.add(ce)`.

### Why It Failed on PostgreSQL
PostgreSQL's stricter ACID compliance and transaction isolation meant that SQLAlchemy didn't automatically detect that the object had been modified unless it was explicitly marked as "dirty" in the session.

## Fix Applied

Added explicit `db.session.add(ce)` call to mark the object as modified:

```python
# Fixed code:
ce = Client_Execution.query.filter_by(client_id=cli_id).first()
if ce:
    ce.elapsed_time += 1
    ce.last_active_hour = h
    ce.last_active_day = d
    db.session.add(ce)  # Explicitly mark as modified for PostgreSQL
    db.session.commit()
```

**Changes Made:**
1. Added `db.session.add(ce)` before `db.session.commit()` to explicitly mark the object as modified
2. Added null check `if ce:` to prevent potential None reference errors
3. This ensures PostgreSQL's session properly tracks and commits the changes

## Verification

### Expected Behavior After Fix
1. **Progress bars update correctly** - Both in `/admin/run_client` and `/admin/dashboard`
2. **last_active_hour and last_active_day** increment properly during simulation
3. **elapsed_time** tracks correctly
4. **Works consistently** across both SQLite and PostgreSQL

### How Progress is Calculated
From `experiments_routes.py` (lines 1328-1348):
```python
client_executions = Client_Execution.query.filter(
    Client_Execution.client_id.in_(client_ids)
).all()

for ce in client_executions:
    # Current position is last_active_day * 24 + last_active_hour
    current_round = ce.last_active_day * 24 + ce.last_active_hour
    remaining = ce.expected_duration_rounds - current_round
    client_progress[ce.client_id] = {
        "expected_rounds": ce.expected_duration_rounds,
        "current_round": current_round,
        "remaining_rounds": max(0, remaining),
    }
```

The progress calculation relies on:
- `expected_duration_rounds`: Total rounds to complete
- `last_active_day`: Current day in simulation
- `last_active_hour`: Current hour in simulation
- `current_round = last_active_day * 24 + last_active_hour`

## Related Issues

This is similar to the agent registration fix (commit 9f280d5) where PostgreSQL's stricter behavior exposed initialization value issues. Both issues stemmed from PostgreSQL's more rigorous enforcement of database semantics compared to SQLite's flexibility.

## Best Practices

When modifying SQLAlchemy model instances:
1. **Always explicitly add to session**: Use `db.session.add(object)` when modifying existing records
2. **Or use bulk updates**: `db.session.query(Model).filter_by(...).update({...})`
3. **Test with PostgreSQL**: PostgreSQL will expose issues that SQLite masks
4. **Check for None**: Always validate query results before modification

## Files Modified
- `y_web/utils/external_processes.py` (lines 1332-1338)

## Testing Recommendations
1. Start an experiment with PostgreSQL
2. Monitor `/admin/run_client/<client_id>/<exp_id>` - progress bar should update
3. Check `/admin/dashboard` - client progress should increment
4. Verify Client_Execution table directly:
   ```sql
   SELECT client_id, last_active_hour, last_active_day, elapsed_time 
   FROM client_execution;
   ```
   Values should increment during simulation.
