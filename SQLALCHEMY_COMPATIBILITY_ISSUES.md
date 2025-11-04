# SQLAlchemy Compatibility Issues: SQLite vs PostgreSQL

## Summary
This document identifies SQLAlchemy query and model definition issues that work on SQLite but fail or behave differently on PostgreSQL.

## Issues Identified

### 1. **client_execution Table**

#### Schema Mismatch Issue
**Model Definition (models.py):**
```python
class Client_Execution(db.Model):
    elapsed_time = db.Column(db.Integer, default=0)
    expected_duration_rounds = db.Column(db.Integer, default=0)  # ❌ default=0 in model
    last_active_hour = db.Column(db.Integer, default=-1)
    last_active_day = db.Column(db.Integer, default=-1)
```

**PostgreSQL Schema:**
```sql
CREATE TABLE client_execution (
    elapsed_time             INTEGER DEFAULT 0 NOT NULL,
    expected_duration_rounds INTEGER NOT NULL,  -- ❌ NOT NULL without default
    last_active_hour         INTEGER NOT NULL,  -- ❌ NOT NULL without default
    last_active_day          INTEGER NOT NULL   -- ❌ NOT NULL without default
);
```

**SQLite Schema:**
```sql
CREATE TABLE client_execution (
    elapsed_time             integer default 0 not null,
    expected_duration_rounds integer not null,  -- Same issue
    last_active_hour         integer not null,  -- Same issue
    last_active_day          integer not null   -- Same issue
);
```

**Problem:**
- Model has `default=0` and `default=-1` for some columns
- Schema has `NOT NULL` without defaults for `expected_duration_rounds`, `last_active_hour`, `last_active_day`
- SQLite is more lenient with constraint violations
- PostgreSQL strictly enforces NOT NULL constraints

**Solution:**
Either:
1. Add defaults to schema to match model, OR
2. Remove defaults from model and ensure values are always provided

### 2. **exps Table**

#### Type Mismatch Issue
**Model Definition (models.py):**
```python
class Exps(db.Model):
    idexp = db.Column(db.Integer, primary_key=True)
    llm_agents_enabled = db.Column(db.Boolean, nullable=False, default=True)  # ❌ Boolean
    status = db.Column(db.Integer, nullable=False)  # ❌ nullable=False without default
```

**PostgreSQL Schema:**
```sql
CREATE TABLE exps (
    idexp              SERIAL PRIMARY KEY,
    llm_agents_enabled INTEGER DEFAULT 1 NOT NULL  -- ❌ INTEGER not BOOLEAN
    status             INTEGER DEFAULT 0,
);
```

**SQLite Schema:**
```sql
CREATE TABLE "exps" (
    idexp integer not null primary key,
    llm_agents_enabled INTEGER DEFAULT 1 NOT NULL  -- INTEGER not BOOLEAN
    status INT default 0,
);
```

**Problems:**
1. **Type mismatch:** Model uses `db.Boolean` but schema uses `INTEGER`
   - SQLite stores Boolean as INTEGER (0/1) so it works
   - PostgreSQL has a native BOOLEAN type, creating type confusion
   
2. **Status default:** Model has `nullable=False` without default, schema has `DEFAULT 0`

**Solution (IMPLEMENTED):**
Changed model to use `db.Integer` instead of `db.Boolean` for cross-database compatibility:
- Model: `llm_agents_enabled = db.Column(db.Integer, nullable=False, default=1)`
- Form handling: Convert boolean to integer (1/0) when creating experiments
- This ensures compatibility with both SQLite and PostgreSQL

### 3. **population_activity_profile Table**

#### Query Pattern Issue
**Current Query (external_processes.py):**
```python
population_activity_profiles = (
    db.session.query(PopulationActivityProfile)
    .filter(PopulationActivityProfile.population == population.id)
    .all()
)
```

**Model Definition:**
```python
class PopulationActivityProfile(db.Model):
    population = db.Column(
        db.Integer, db.ForeignKey("population.id", ondelete="CASCADE"), nullable=False
    )
```

**Problem:**
- Using `==` for comparison works but may have subtle differences between databases
- No explicit handling of NULL values
- PostgreSQL is stricter with type coercion

**Solution:**
Use more explicit comparison:
```python
population_activity_profiles = (
    db.session.query(PopulationActivityProfile)
    .filter(PopulationActivityProfile.population == population.id)
    .all()
)
```
Current code is actually correct. Issue might be elsewhere.

## Recommended Fixes

### Priority 1: Fix client_execution Schema

**Option A: Add defaults to schema (Recommended)**
```sql
CREATE TABLE client_execution (
    id                       SERIAL PRIMARY KEY,
    elapsed_time             INTEGER DEFAULT 0 NOT NULL,
    client_id                INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    expected_duration_rounds INTEGER DEFAULT 0 NOT NULL,
    last_active_hour         INTEGER DEFAULT -1 NOT NULL,
    last_active_day          INTEGER DEFAULT -1 NOT NULL
);
```

**Option B: Update model to remove defaults**
```python
class Client_Execution(db.Model):
    elapsed_time = db.Column(db.Integer, default=0, nullable=False)
    expected_duration_rounds = db.Column(db.Integer, nullable=False)  # Remove default
    last_active_hour = db.Column(db.Integer, nullable=False)  # Remove default
    last_active_day = db.Column(db.Integer, nullable=False)  # Remove default
```

### Priority 2: Fix exps Table Type Mismatch

**Option A: Change model to INTEGER (Recommended for compatibility)**
```python
class Exps(db.Model):
    llm_agents_enabled = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.Integer, nullable=False, default=0)
```

**Option B: Change schema to BOOLEAN**
```sql
CREATE TABLE exps (
    ...
    llm_agents_enabled BOOLEAN DEFAULT TRUE NOT NULL,
    status             INTEGER DEFAULT 0 NOT NULL,
    ...
);
```

### Priority 3: Add Explicit nullable Flags

Ensure all models explicitly declare `nullable=True` or `nullable=False` to match schema constraints.

## Testing Recommendations

1. Test INSERT operations without providing optional values
2. Test queries with NULL comparisons
3. Test Boolean/Integer conversions
4. Verify foreign key constraint behavior
5. Test with both SQLite and PostgreSQL databases

## Common PostgreSQL vs SQLite Differences

1. **Type Strictness:** PostgreSQL enforces types strictly, SQLite is more flexible
2. **NULL Handling:** PostgreSQL has stricter NULL constraint enforcement
3. **Boolean Type:** SQLite doesn't have native BOOLEAN, uses INTEGER (0/1)
4. **String Quoting:** PostgreSQL prefers single quotes for strings, double quotes for identifiers
5. **SERIAL vs AUTOINCREMENT:** PostgreSQL uses SERIAL, SQLite uses AUTOINCREMENT
6. **Default Values:** PostgreSQL requires explicit defaults for NOT NULL columns without them

## Action Items

- [ ] Update postgre_dashboard.sql with correct defaults for client_execution
- [ ] Update Exps model to use Integer instead of Boolean for llm_agents_enabled
- [ ] Add status default to Exps model
- [ ] Test all INSERT operations on PostgreSQL
- [ ] Verify all queries work on both databases
