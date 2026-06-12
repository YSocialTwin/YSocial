# Adhoc and HPC Failure Analysis Report

## Scope

This report covers the failure modes observed in adhoc agents and HPC simulation runs, the fixes applied across the codebase, and the expected regression impact.

## Observed Failures

### 1. SQLite `RETURNING` not supported

**Symptoms**
- Adhoc agent execution failed during post/message creation with:
  - `sqlalchemy.exc.CompileError: RETURNING is not supported by this dialect's statement compiler`

**Root cause**
- The SQLite dialect in the runtime did not support `INSERT ... RETURNING`.
- The database layer used a path that assumed returning primary keys was available.

**Fix**
- Removed `RETURNING` usage from insert paths in `external/y_agents_plugins`.
- Switched to explicit insert + fallback lookup patterns where needed.

### 2. Foreign key mismatch / wrong topic payload

**Symptoms**
- `post_topics` inserts failed with values such as:
  - `INSERT INTO post_topics (post_id, topic_id) VALUES (?, ?)`
  - parameters: `(46, 'dsa')`
- This was followed by foreign key mismatch errors.

**Root cause**
- Topic labels were being passed through as strings instead of being resolved to runtime topic IDs.
- Some schema variants store topic keys as integer IDs, while others use UUID/text identifiers.

**Fix**
- Normalized topic IDs in the shared executor layer before `post_topics` inserts.
- Updated topic resolution to fall back safely when configured values are strings.
- Added regression coverage for string topic labels like `dsa`.

### 3. Duplicate adhoc agent registration

**Symptoms**
- Adhoc clients produced duplicate `user_mgmt` rows, including one extra lowercase `hoid` record.

**Root cause**
- The adhoc runner registered both:
  - the managed agent list from configuration
  - the runtime client agent itself
- The runtime client agent should not be persisted as a separate user row.

**Fix**
- Removed the runtime client agent from the `register_agents()` batch.
- Kept only the configured managed agents in `user_mgmt`.
- Removed the hardcoded `owner = "experiment"` default from the adhoc client spec builder.

### 4. SQLite lock during plugin table creation

**Symptoms**
- Adhoc startup failed while plugins were creating schema objects:
  - `database is locked`
  - failures in `moderator.setup_database()` and `stress_attacker.setup_database()`

**Root cause**
- The adhoc runner had an active connection/transaction when plugin `setup_database()` performed DDL.
- SQLite locks aggressively during DDL and concurrent writes.

**Fix**
- Wrapped plugin setup in the existing SQLite retry helper.
- Explicitly committed or rolled back before plugin DDL.
- This reduces lock contention during adhoc startup.

### 5. SQLite lock during round creation in HPC

**Symptoms**
- HPC logs showed:
  - `Error getting or creating round: (sqlite3.OperationalError) database is locked`
  - failing on `INSERT INTO rounds (...)`

**Root cause**
- Multiple writers were using the same SQLite-backed experiment database.
- Round creation was a direct write with no retry logic.

**Fix**
- Added rollback + retry handling to `SQLRecommendationRepository.get_or_create_round()`.
- Added a regression test for the locked-round path.

## Impact Assessment

### Positive impact

- Adhoc agent startup is more reliable.
- Adhoc posts/comments/shares now resolve topic IDs consistently across schema variants.
- Duplicate adhoc `user_mgmt` rows are prevented.
- Plugin schema creation is less likely to fail on SQLite contention.
- HPC round creation now tolerates transient SQLite lock contention.

### Regression risk evaluation

The changes were limited to failure-prone boundaries:
- insert/update helpers
- adhoc runner bootstrap
- simulator round creation

The following behaviors were preserved:
- existing plugin action generation
- current topic semantics for propaganda and master-of-puppets campaigns
- existing user registration behavior for real managed agents
- current repository interfaces and call sites

### Compatibility notes

- The fixes are compatible with both integer-backed and text-backed topic identifiers.
- SQLite contention is reduced, but SQLite still remains a single-writer database.
- If many clients or adhoc agents write concurrently, transient lock retries help but do not eliminate the architectural limit.

## Regression Verification

Validated with targeted tests during the fix cycle:

- `external/y_agents_plugins/tests/test_executor.py`
  - `47 passed`
- `external/YSimulator/YSimulator/tests/test_repositories.py -k 'get_or_create_round'`
  - `5 passed`
- Adhoc runner syntax validation
  - `python -m py_compile y_web/src/simulation/adhoc_client_runner.py`

## Residual Risk

SQLite still has a hard single-writer constraint. If future workloads increase concurrent writes from:
- multiple adhoc clients
- multiple HPC clients
- background cleanup jobs
- startup DDL

then the remaining risk is lock contention under sustained load.

## Recommended Follow-up

1. Keep the retry guards already added.
2. Move schema creation out of runtime paths where possible.
3. Prefer a single writer or queued write model for shared SQLite databases.
4. Migrate HPC/shared simulation workloads to a server database if concurrency remains high.

