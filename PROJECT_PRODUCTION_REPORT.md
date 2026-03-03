# YWeb Production Readiness Report

## Scope
This report summarizes potential issues, reliability/performance improvements, and an implementation pipeline to move the current YWeb codebase toward production-grade operations.

## Potential Bugs And Issues

### 1. Long-running request handlers for archive generation
- **Observed risk:** experiment download endpoints were historically synchronous, coupling heavy ZIP generation to the HTTP request lifecycle.
- **Impact:** browser timeouts, interrupted downloads (`.crdownload` leftovers), server worker starvation.
- **Status:** fixed in current changes by introducing asynchronous archive generation with notifications.

### 2. Repeated complex DB-export logic in request paths
- **Observed risk:** PostgreSQL->SQLite copy logic is duplicated in multiple code paths and is error-prone.
- **Impact:** behavior drift and hard-to-debug export failures.
- **Recommendation:** centralize export logic into a dedicated service module with tests (unit + integration).

### 3. Incomplete lifecycle management of temporary files
- **Observed risk:** temp archive accumulation in `y_web/experiments/temp_data`.
- **Impact:** disk growth and degraded host stability over time.
- **Status:** partially addressed by cancellation cleanup; still missing TTL-based housekeeping for stale files.

### 4. Large route modules with mixed responsibilities
- **Observed risk:** `y_web/routes_admin/experiments_routes.py` handles orchestration, storage, and UI response concerns.
- **Impact:** regression risk and reduced maintainability.
- **Recommendation:** split into service layers (`experiment_export_service`, `notification_service`, `experiment_lifecycle_service`).

### 5. Limited failure observability
- **Observed risk:** failures rely mostly on app logs/flash messages.
- **Impact:** hard to detect repeated operational failures.
- **Recommendation:** add structured telemetry for async jobs (queued, started, completed, failed, cancelled).

### 6. Concurrency behavior not yet formally tested
- **Observed risk:** background threads update shared DB entities without dedicated stress tests.
- **Impact:** edge race conditions around cancellation/ready status.
- **Recommendation:** add tests for notification state transitions under concurrent operations.

## Improvements For Efficiency And Stability

## A. Platform and Runtime
- Add a production WSGI stack (`gunicorn`/`uwsgi`) with tuned worker/thread config.
- Introduce reverse proxy buffering/timeouts (Nginx/Caddy) and static asset caching.
- Externalize secrets and DB credentials using environment-based config only.

## B. Async Work Execution
- Move from in-process threads to a job queue (Celery/RQ/Arq) backed by Redis.
- Add retry policies, job timeouts, dead-letter strategy, and idempotent job keys.
- Add periodic cleanup task for `temp_data` archives older than configurable TTL.

## C. Data Layer
- Add indexes for hot admin queries and notification lookups.
- Enforce DB constraints for status/state columns (check constraints or enum patterns).
- Run migration consistency checks in CI.

## D. Quality and Testing
- Add automated tests for:
  - async download queueing,
  - cancellation cleanup,
  - notification permissions,
  - stale file handling,
  - bulk delete payload modes (`list`, `all`, `group`).
- Add contract tests for admin endpoints returning JSON payloads used by UI polling.

## E. Security and Operations
- Validate all user-provided names used in file naming and export metadata.
- Add rate limiting for heavy endpoints.
- Add audit log records for deletion and download operations.
- Add health endpoint coverage for background worker status.

## F. Frontend UX Resilience
- Show explicit job states: `queued`, `processing`, `ready`, `failed`, `cancelled`.
- Add optimistic UI updates after mark-read/cancel actions.
- Add pagination/search on full notification page for high volume.

## Organized Pipeline To Implement Fixes

## Phase 0: Baseline (1-2 days)
1. Freeze current behavior and capture baseline metrics (request latency, error rates, disk use in `temp_data`).
2. Document architecture boundaries and critical paths.
3. Define SLOs: admin page latency, export success rate, queue completion target.

## Phase 1: Stabilization (2-4 days)
1. Complete async export rollout and remove blocking download paths.
2. Add notification lifecycle tests and permission checks.
3. Add scheduled cleanup for stale temp archives.
4. Harden delete flows (`single`, `all`, `group`) with backend validation.

## Phase 2: Service Extraction (4-7 days)
1. Move export/copy/compress logic to `services/exports.py`.
2. Move notification CRUD/state transitions to `services/notifications.py`.
3. Keep routes as thin orchestrators.
4. Add unit tests per service with mocking for filesystem and DB.

## Phase 3: Production Hardening (1-2 weeks)
1. Introduce external queue (Redis + worker) for exports.
2. Add structured logs + telemetry dashboard (job latency/failures).
3. Add CI gates: lint, tests, migration checks, smoke test.
4. Add backup/restore drill for dashboard DB and experiment assets.

## Phase 4: Scale and Operability (ongoing)
1. Add role-based audit events and anomaly alerts.
2. Add capacity management for `temp_data` and experiment artifacts.
3. Add disaster recovery runbook and on-call playbook.

## Path Toward Production-Grade
- **Short term:** keep current async notifications architecture, add tests + cleanup + validation.
- **Mid term:** replace thread-based jobs with queue workers and isolate business services.
- **Long term:** standardize deployment/monitoring with SLO-driven operations, CI/CD gates, and disaster recovery procedures.

## Immediate Action Checklist
1. Merge current async notification/download changes.
2. Add automated tests for notification lifecycle and async archive outcomes.
3. Add stale archive cleanup task.
4. Schedule service extraction from `experiments_routes.py`.
5. Introduce external worker queue in staging and load-test it.
