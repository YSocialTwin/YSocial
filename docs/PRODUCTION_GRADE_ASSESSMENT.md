# YWeb Production-Grade Assessment

Date: 2026-02-20  
Scope: Static code/config review + focused test execution  
Repository: `/Users/rossetti/PycharmProjects/YWeb`

## 1. Executive Summary

The project is feature-rich and has a broad test suite, but it is not yet production-grade for multi-user, internet-facing deployment.  
The highest risks are in security hardening, runtime isolation, and operational reliability.

Key blockers before production:
- Sensitive security defaults and data exposure in admin endpoints.
- Mutable global DB bind switching per request (race-condition risk under concurrency).
- Dev-oriented runtime model (`app.run`, startup side effects, best-effort exception swallowing).
- Build/deploy setup not reproducible or hardened (Docker + dependency strategy).

## 2. What Was Analyzed

- Runtime/bootstrap: `/Users/rossetti/PycharmProjects/YWeb/y_web/__init__.py`, `/Users/rossetti/PycharmProjects/YWeb/y_social.py`, `/Users/rossetti/PycharmProjects/YWeb/y_web/experiment_context.py`
- Core routes/auth: `/Users/rossetti/PycharmProjects/YWeb/y_web/auth.py`, `/Users/rossetti/PycharmProjects/YWeb/y_web/main.py`, `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/users_routes.py`
- Process control: `/Users/rossetti/PycharmProjects/YWeb/y_web/utils/external_processes.py`
- Delivery/config: `/Users/rossetti/PycharmProjects/YWeb/Dockerfile`, `/Users/rossetti/PycharmProjects/YWeb/docker-compose*.yml`, `/Users/rossetti/PycharmProjects/YWeb/requirements.txt`, `/Users/rossetti/PycharmProjects/YWeb/.github/workflows/*.yml`
- Source hygiene: `/Users/rossetti/PycharmProjects/YWeb/.gitignore`

Focused tests executed:
- `pytest -q y_web/tests/test_app_structure.py` (13 passed)
- `pytest -q y_web/tests/test_auth_routes.py` (12 passed, SQLAlchemy legacy warnings)
- `pytest -q y_web/tests/test_admin_routes.py` (13 passed, SQLAlchemy legacy warnings)

## 3. Potential Bugs and Issues

## Critical

1. Admin password hashes exposed via API response
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/users_routes.py:133`
- Risk: Credential hash leakage facilitates offline cracking and account takeover attempts.
- Fix: Remove `password` from API payloads entirely.

2. Password updates can be stored unhashed
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/users_routes.py:185` to `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/users_routes.py:188`
- Risk: The generic update endpoint sets `password` directly without `generate_password_hash`.
- Fix: Block `password` in generic update endpoint; route all password changes through dedicated validated hashing flow.

3. Hardcoded secret key
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/__init__.py:305`
- Risk: Session/cookie forgery if key is known.
- Fix: Require `SECRET_KEY` from env/secret manager, fail fast if missing in production mode.

4. Missing CSRF protection for state-changing endpoints
- Evidence: no `CSRFProtect` initialization in app bootstrap; multiple POST routes rely only on session auth.
- Risk: Browser-based CSRF against authenticated admins/researchers.
- Fix: Enable CSRF globally for forms and token validation for JSON endpoints.

## High

5. Global mutable DB bind switching per request
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/experiment_context.py:109` to `/Users/rossetti/PycharmProjects/YWeb/y_web/experiment_context.py:114`
- Risk: Under concurrent requests, bind mutation in shared app config can cross-wire data between experiments.
- Fix: Replace with per-request scoped sessions/engines or explicit bind/session routing (no global config mutation).

6. Authentication/session flow mutates global bind during login path
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/auth.py:187` to `/Users/rossetti/PycharmProjects/YWeb/y_web/auth.py:212`
- Risk: Same cross-request race pattern during experiment selection.
- Fix: Query experiment DB via dedicated engine/session context, not by overriding `SQLALCHEMY_BINDS["db_exp"]`.

7. Potential profile follow-state bug (ID namespace mismatch)
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/main.py:183` to `/Users/rossetti/PycharmProjects/YWeb/y_web/main.py:185`
- Risk: Uses `current_user.id` for follower checks even when logged identity is resolved separately as `logged_id`; can return wrong follow state.
- Fix: Use `logged_id` consistently for experiment DB entities.

8. Startup/shutdown side effects and noisy failures in tests/runtime
- Evidence: scheduler startup at app creation `/Users/rossetti/PycharmProjects/YWeb/y_web/__init__.py:1094` to `:1100`, atexit cleanup registration `/Users/rossetti/PycharmProjects/YWeb/y_web/__init__.py:279`
- Observed: during tests, cleanup emits `"can't register atexit after shutdown"`.
- Risk: unpredictable shutdown behavior, difficult operational debugging.
- Fix: gate side effects by runtime mode; isolate scheduler lifecycle to explicit process entrypoints.

## Medium

9. Broad exception swallowing (`except:` / `except Exception: pass`) across hot paths
- Evidence: many instances in `/Users/rossetti/PycharmProjects/YWeb/y_web/main.py` and `/Users/rossetti/PycharmProjects/YWeb/y_web/data_access.py`
- Risk: hides failures, makes incident detection and root-cause analysis hard.
- Fix: catch specific exceptions, log structured context, return explicit fallback states.

10. Legacy SQLAlchemy API usage surfacing in tests
- Evidence: warnings in `test_auth_routes` and `test_admin_routes` for `Query.get()`.
- Risk: upgrade friction and future breakage with SQLAlchemy 2.x migration.
- Fix: migrate to `db.session.get(Model, id)` and modern query patterns.

11. Deprecated shell-based process startup still present
- Evidence: `/Users/rossetti/PycharmProjects/YWeb/y_web/utils/external_processes.py:2462`, `:2550`, `:2699`
- Risk: shell injection surface and operational inconsistency (even if marked deprecated).
- Fix: remove or hard-disable deprecated shell-based code paths.

12. Repository hygiene and artifact sprawl
- Evidence: huge untracked experiment/runtime assets in `y_web/experiments/*`; `.gitignore` does not exclude these paths.
- Risk: accidental commits, larger diffs, slower CI, reduced reproducibility.
- Fix: ignore runtime-generated artifacts and define explicit data retention/export policies.

## 4. Efficiency and Stability Improvements

1. Split monolithic modules
- `y_web/main.py` (~2109 lines), `y_web/data_access.py` (~1495), `y_web/utils/external_processes.py` (~3159), `y_web/routes_admin/users_routes.py` (~1304)
- Move to bounded contexts (auth/profile/feed/admin/process orchestration) to improve maintainability and testability.

2. Reduce N+1 query patterns and repeated DB lookups
- Example areas: profile/feed aggregation paths in `main.py` and `data_access.py`.
- Add eager loading and batched queries for reactions/comments/user metadata.

3. Replace dev server runtime with production WSGI/ASGI profile
- Current path uses `app.run(...)` in `y_social.py`.
- Standardize production entrypoint with `gunicorn` config, worker class selection, timeouts, graceful shutdown, health probes.

4. Harden dependency management
- `requirements.txt` mixes runtime/dev/test deps, duplicates `requests`, and pins older framework stack.
- Split into `requirements/base.txt`, `requirements/dev.txt`, `requirements/prod.txt`.
- Introduce lock generation (`pip-tools`/`uv`) and scheduled dependency update checks.

5. Container hardening and reproducibility
- Avoid `ubuntu:latest`; pin digest/tag and use multi-stage build.
- Remove runtime install scripts during image build where possible (e.g., curl-to-shell patterns).
- Run as non-root user and drop unnecessary packages.

6. Observability foundation
- Introduce structured logging (JSON), request IDs, standard error taxonomy.
- Export basic metrics: request latency, DB query latency, background task status, process lifecycle events.

7. Security controls
- Rate-limiting on auth/admin endpoints.
- Secure cookie flags (`HttpOnly`, `Secure`, `SameSite`), session lifetime policy, brute-force mitigation.
- Secrets management via env vault/injected secrets, never hardcoded defaults.

## 5. Implementation Pipeline (Organized)

## Phase 0: Stabilize and Protect (Week 1)
- Remove exposed `password` fields from responses.
- Block raw password writes in generic admin update route.
- Move `SECRET_KEY` and default credentials to secure configuration flow.
- Add CSRF protection and baseline secure session cookie config.
- Deliverables: patched routes, security config, regression tests for the above.

## Phase 1: Runtime Correctness (Weeks 1-2)
- Eliminate global bind mutation model in request handling/auth.
- Introduce explicit per-request/per-experiment DB session strategy.
- Add concurrency tests for simultaneous multi-experiment requests.
- Deliverables: DB routing refactor + stress tests.

## Phase 2: Operational Hardening (Weeks 2-3)
- Replace `app.run` production path with `gunicorn` process model.
- Isolate startup side effects (release checks, blog checks, schedulers) behind feature flags and explicit lifecycle hooks.
- Ensure clean startup/shutdown behavior in tests and production.
- Deliverables: production runtime profile + lifecycle tests.

## Phase 3: Codebase Refactor for Efficiency (Weeks 3-6)
- Break down oversized modules.
- Remove deprecated shell-based process helpers.
- Optimize top query hotspots and add performance baselines.
- Deliverables: modularized services + measurable latency/query improvements.

## Phase 4: CI/CD and Quality Gates (Weeks 4-6)
- Add lint/type/security gates (`ruff`, `mypy`, `bandit`, `pip-audit`/equivalent).
- Add smoke integration tests for Docker + DB matrix.
- Enforce branch protections and required checks.
- Deliverables: reproducible CI with merge blockers on security/test failures.

## Phase 5: Production Readiness and Rollout (Weeks 6-8)
- Container hardening + immutable versioned images.
- Staging environment with canary rollout.
- Runbook: backup/restore, incident response, SLOs, on-call handoff.
- Deliverables: go-live checklist, rollback plan, SLO dashboard.

## 6. Target Production Architecture (Path Forward)

- App runtime: `gunicorn` workers behind Nginx/reverse proxy.
- DB layer: explicit engine/session routing per experiment; no global mutable bind.
- Background jobs: isolated worker process(es) for scheduler/monitoring tasks.
- Secrets/config: environment + secret manager, strict config validation at startup.
- Observability: structured logs + metrics + alerting (errors, latency, scheduler failures).
- Release model: staged deploys, migration gating, health checks, automated rollback trigger.

## 7. Suggested Acceptance Criteria

Security:
- No credential material in API responses.
- No hardcoded secrets/default production credentials.
- CSRF and secure session policies enabled.

Correctness:
- Multi-experiment concurrent requests pass isolation tests.
- No global bind mutation in request path.

Reliability:
- Clean startup/shutdown without side-effect races.
- 95th percentile request latency and error budget thresholds defined and monitored.

Quality:
- CI enforces tests, lint, type checks, and dependency/security scans.
- Reproducible builds with pinned dependency locks and pinned base images.

## 8. Immediate Next 10 Tasks (Execution Order)

1. Patch `/admin/user_data` response to remove password hash field.
2. Disallow `password` in generic update endpoint; require dedicated password endpoint.
3. Externalize `SECRET_KEY`; add startup validation.
4. Enable CSRF protection and update forms/AJAX clients.
5. Add tests for unauthorized access and password handling regression.
6. Refactor experiment DB access away from mutable `SQLALCHEMY_BINDS["db_exp"]`.
7. Add concurrent-request isolation tests.
8. Split runtime and dev dependencies into separate requirement sets.
9. Create production `gunicorn` startup config and container entrypoint.
10. Add CI security/quality gates and artifact hygiene rules.

