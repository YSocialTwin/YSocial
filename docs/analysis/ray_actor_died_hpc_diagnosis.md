# HPC / Microblogging Ray actor death diagnosis

Date: 2026-07-06

## Problem statement

Occasionally, especially when experiments are launched in batch, HPC-style microblogging simulations stop making progress while the Flask UI still shows them as running. The terminal shows a Ray `ActorDiedError` / `ray actor died` message, but the application logs often remain empty or inconclusive.

A common recovery pattern is:
1. Stop the experiment.
2. Wait a bit.
3. Start it again.

That usually works unless other HPC experiments are already running, which strongly suggests a shared runtime/resource problem rather than a purely local one-off corruption.

## What the code is doing today

### 1) The server is allowed to reuse an existing Ray cluster

The external server entry point explicitly prefers `ray.init(address="auto")` when `server.address` is left at the default `auto` value:

- `external/YSimulator/run_server.py:340-407`

That means separate experiments can end up sharing the same local Ray cluster if it is already alive.

The server then writes two files into the experiment folder:

- `ray_config.temp` (Ray address)
- `ray_namespace.temp` (namespace)

See:

- `external/YSimulator/run_server.py:426-432`

### 2) Namespace isolation exists, but only for the server/orchestrator path

The server tries to detect whether the current namespace already contains an `Orchestrator` actor and, if so, switches to a hashed namespace derived from the config directory:

- `external/YSimulator/run_server.py:386-407`

This is a useful guard, but it only protects the `Orchestrator` actor registration path. It does not make the whole Ray runtime experiment-isolated.

### 3) The client connects to the Ray address + namespace, but then creates more Ray actors

The client reads `ray_config.temp`, resolves the namespace, and calls:

- `ray.init(address=ray_address, namespace=namespace, ignore_reinit_error=True)`

See:

- `external/YSimulator/run_client.py:430-434`

Then it creates:

- the LLM service / actor pool
- the news feed service
- the simulation client actor itself

See:

- `external/YSimulator/run_client.py:459-672`

### 4) The simulation client and news service both depend on `ray.get_actor("Orchestrator")`

The client side and news service side both look up the `Orchestrator` actor by name:

- `external/YSimulator/YSimulator/YClient/client.py:291-293`
- `external/YSimulator/YSimulator/YClient/news_feeds/news_service.py:103-109`

There is no explicit namespace argument in those lookups. They rely on the current Ray namespace being exactly right.

### 5) The LLM layer can create detached, named actors and reuse them across runs

The load balancer supports named actors, detached actors, and shared pools. The important parts are:

- namespace resolution: `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:53-62`
- shared pool key construction: `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:85-108`
- lease registry and pool reservation: `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:1116-1310`
- fallback single-actor / reuse logic: `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:1226-1310` and `1380-1490`

This is powerful, but it also means actor lifetime can extend beyond one client process, and a bad actor state can survive long enough to affect later experiments.

## Why the UI still says "running"

The Flask side tracks the outer subprocess PID and the experiment/client DB flags, but it does **not** supervise Ray actor health directly.

Relevant files:

- `y_web/src/hpc/client.py:26-116` (PID liveness and stale PID clearing)
- `y_web/src/hpc/log_metrics.py:644-795` (completion detection based on logs + DB state)

That means the web app can still believe an experiment is active even if an inner Ray actor has already died, especially if:

- the outer subprocess is still alive,
- a child actor died inside Ray,
- no explicit error path propagated back into the monitoring tables,
- the logs only contain the generic Ray failure message.

## Most likely failure mode

The most likely root cause is a combination of:

1. **Shared Ray cluster reuse** (`ray.init(address="auto")`) across experiments.
2. **Partial isolation only** (namespace isolation for `Orchestrator`, but not a full experiment-scoped runtime for every actor).
3. **Detached / reusable Ray actors** in the LLM layer.
4. **Resource pressure** when multiple HPC experiments run at once.

In that situation, a nested Ray actor can die because of:

- memory pressure / OOM,
- GPU contention,
- stale actor reuse,
- namespace or actor-name collision,
- or a server/client attach order that leaves one actor looking up another before the runtime is fully ready.

The failure is then visible only as a Ray `ActorDiedError`, while the outer process and DB state can remain stale.

## Why stopping and restarting later often helps

Stopping the experiment typically clears one or more of the following:

- stale detached actors,
- lease registry state,
- old namespace leftovers,
- process/PID records,
- resource exhaustion from competing experiments.

If other HPC experiments are still running, the restart can fail again because the underlying contention has not been removed.

That behavior strongly supports a **shared runtime / resource contention** hypothesis rather than a pure one-experiment config bug.

## Evidence in the codebase

### Ray cluster reuse and namespace isolation

- `external/YSimulator/run_server.py:340-407`
- `external/YSimulator/run_server.py:426-432`

### Client startup and Ray attachment

- `external/YSimulator/run_client.py:430-434`
- `external/YSimulator/run_client.py:459-672`

### Orchestrator lookup without explicit namespace

- `external/YSimulator/YSimulator/YClient/client.py:291-293`
- `external/YSimulator/YSimulator/YClient/news_feeds/news_service.py:103-109`

### Shared / detached actor lifecycle

- `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:53-62`
- `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:1116-1310`
- `external/YSimulator/YSimulator/YClient/llm_utils/load_balancer.py:1380-1490`

### Process/PID monitoring does not supervise inner Ray actors

- `y_web/src/hpc/client.py:26-116`
- `y_web/src/hpc/log_metrics.py:644-795`

## Proposed fix strategy

I would not patch the symptom in only one place. The fix should be architectural and should make the Ray runtime experiment-scoped.

### Fix 1: Make Ray lifecycle explicitly experiment-scoped

Recommended approach:

- Use a unique Ray namespace per experiment, not just for `Orchestrator`, but for all experiment-owned actors.
- Persist a small runtime metadata file in the experiment folder containing:
  - Ray address
  - namespace
  - experiment identity / config path digest
  - server actor name
- Refuse to start a client if the namespace does not match the current experiment metadata.

### Fix 2: Add actor health checks / heartbeat

The monitor should not rely only on:

- PID liveness,
- DB flags,
- and log tail parsing.

It should also probe the Ray side:

- `ray.get_actor("Orchestrator", namespace=...)`
- a lightweight `ping()` / heartbeat method on the server actor
- optionally a client heartbeat method or a small supervisory actor

If a probe fails, mark the experiment as failed/stopped instead of leaving it indefinitely marked as running.

### Fix 3: Make actor names and pools fully experiment-aware

The current shared LLM logic is powerful but too permissive for batch HPC runs.

Recommendations:

- Include `experiment_identity` in every named actor/pool key.
- Avoid reusing detached actors across unrelated experiments unless the user explicitly opts in.
- Validate metadata before reuse (model, backend, namespace, actor count, prompt/config fingerprint).

### Fix 4: Fail fast and log the real Ray exception

If a nested Ray actor dies:

- write the exception into the experiment logs,
- propagate a structured failure state into the DB,
- stop the experiment cleanly,
- do not leave the UI in a "running" state.

## Expected outcome after the fix

After these changes:

- a dead Ray actor would be detected quickly,
- the experiment would transition to a failed/stopped state instead of hanging,
- restarting would no longer depend on manually waiting for stale Ray state to expire,
- concurrent HPC experiments would not interfere with each other as easily.

## Final assessment

The evidence points to a **Ray runtime isolation / actor lifecycle problem**, not to a simple logging bug.

The most likely issue is that experiments share too much of the same Ray runtime surface area, while the Flask side only supervises subprocesses and database status. That allows a Ray actor to die silently from the application’s point of view.

The durable fix is to make experiment isolation explicit at the Ray level and to add actor health supervision, rather than relying only on PIDs and log parsing.
