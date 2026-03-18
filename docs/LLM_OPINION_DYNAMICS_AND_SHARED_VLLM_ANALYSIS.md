# LLM Opinion Dynamics + Shared vLLM Pool Analysis

## Scope
This report answers:
1. Whether LLM-based opinion dynamics currently uses batching when `vllm` is selected.
2. Feasibility of running multiple clients (including from different experiments) on the same vLLM instance/pool, with explicit selection of an existing instance.

## Evidence Summary (Code References)
- vLLM backend selection and actor reuse parameters are written in HPC client config:
  - `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/clients_routes.py:781`
  - `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/clients_routes.py:796`
  - `/Users/rossetti/PycharmProjects/YWeb/y_web/routes_admin/clients_routes.py:1015`
- Client runtime reads namespace from config and initializes Ray namespace per client run:
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/run_client.py:365`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/run_client.py:367`
- vLLM batching is used for posts/comments/reads/emotions in batch processor:
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:136`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:453`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:963`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:1273`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:1780`
- Opinion dynamics path currently calls single-evaluation LLM calls per interaction:
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/opinion_dynamics/llm_evaluation.py:119`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/opinion_dynamics/llm_evaluation.py:127`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/llm_utils/llm_manager.py:342`
- Batch processor explicitly says opinion batching is still standard path (not true LLM batch):
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:1844`
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/simulation/batch_processor.py:1845`
- vLLM has an implemented `evaluate_opinion_batch(...)`, but it is not called by runtime code:
  - `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator/YSimulator/YClient/LLM_interactions/vllm_service.py:2184`

## 1) Does LLM opinion dynamics use batching with vLLM?
Short answer: **No, not in the effective runtime path.**

### What is batched today
When vLLM is active, the batch processor uses batch methods for:
- post generation
- comment/share generation
- read reaction generation
- emotion extraction

### What is not batched today
For opinion dynamics (`model_name = llm_evaluation`):
- The update logic calls `llm_manager.evaluate_opinion(...)` per interaction.
- `llm_manager.evaluate_opinion(...)` dispatches `llm_actor.evaluate_opinion.remote(...)` (single call).
- `_batch_evaluate_and_update_opinions(...)` currently loops over requests and calls the existing single-item pipeline.

Conclusion: the code has **batch-aware scaffolding** for opinion updates, but currently executes a **serial/standard per-request LLM evaluation path**.

## 2) Feasibility of sharing one vLLM instance across multiple clients/experiments
Short answer: **Feasible**, with moderate changes. There is already a partial foundation.

### What already exists (partial capability)
- HPC form already exposes:
  - `num_actors`
  - `gpu_per_actor`
  - `reuse_actors`
  - `actor_name_prefix`
- Runtime load balancer already supports actor discovery by name and reuse:
  - `ray.get_actor(f"{actor_name_prefix}_{backend}_{i}")`
- Actors are created as detached named actors when reuse path is used.

This is enough to share actors among clients **in the same namespace** with aligned configuration.

### Why cross-experiment sharing is limited now
- Client namespace is set from simulation config `namespace`, currently bound to experiment name at generation time.
- Different experiments therefore typically run in different Ray namespaces.
- Current actor lookup does not pass an explicit target namespace for shared pools.

Result: cross-experiment reuse is not reliably achievable with current defaults.

## Proposed Solution

## Target behavior
Allow a user, at HPC client creation/update time, to choose:
1. `Dedicated pool` (existing behavior, isolated).
2. `Shared pool` (reuse/create in a named global pool), including selecting **which pool**.

### Data/Config model
Add shared pool fields in client `llm` config:
- `pool_mode`: `dedicated | shared`
- `pool_id`: stable logical ID
- `reuse_actors`: bool (already present)
- `actor_name_prefix`: string (already present)
- `actor_namespace`: string (new; e.g. `ysim_llm_pool`)
- `num_actors`, `gpu_per_actor` (already present)

Add server-side pool registry table (recommended):
- `id`, `name`, `namespace`, `actor_name_prefix`, `backend`, `model_fingerprint`, `num_actors`, `gpu_per_actor`, `status`, `owner`, timestamps.

`model_fingerprint` should encode model-critical params to prevent incompatible sharing.

### Runtime changes (YSimulator)
1. Extend actor discovery/creation utilities (`load_balancer.py`) to operate against explicit `actor_namespace` for both lookup and creation.
2. In shared mode:
- strict reuse: if pool is selected but actors missing/misaligned, fail fast (no silent replacement).
- no implicit recreation with conflicting names.
3. Add compatibility checks before attach:
- backend/model/tensor_parallel/max_model_len/sampling profile.
4. Add pool-level telemetry and health checks.

### UI/UX changes (YWeb)
1. In `admin/clients_hpc` LLM section:
- add `LLM Pool Mode` toggle (`Dedicated` / `Shared`).
- if `Shared`: show `Select existing pool` dropdown + readonly pool config summary.
- optional `Create new shared pool` action.
2. Add pool management page under admin/account:
- list pools, attached clients, status, GPU usage estimate.
- allow controlled shutdown/restart and “detach all” operations.

### Safety and operational constraints
- Do not allow sharing across incompatible model fingerprints.
- Add max concurrent request guard per pool to avoid GPU OOM from contention.
- Ensure lifecycle ownership is clear (pool survives client stop; explicit cleanup action required).
- Handle partial actor discovery robustly (current code warns and then tries to create a full new set; this can conflict with existing names and should be hardened).

## Specific answer to the user scenario
"Multiple clients, even from different experiments, should run on same vLLM instance, selecting existing one":
- **Feasible and aligned** with current architecture.
- Requires explicit pool namespace + registry + strict attach semantics.
- Without namespace and registry changes, behavior is unreliable across experiments.

## Recommended implementation pipeline
1. **Design & schema**
- Add `llm_pools` table and `llm` config extensions.
- Define model fingerprint rules.
2. **Runtime foundation**
- Add namespace-aware actor lookup/creation.
- Implement strict shared attach flow and compatibility validation.
3. **Admin UI**
- Add pool selector in HPC client form.
- Add pool management page with health/status.
4. **Client creation/update wiring**
- Persist selected pool config into generated client JSON.
- Enforce constraints server-side on submit.
5. **Opinion dynamics batching upgrade** (separate but high-impact)
- Route opinion requests to `evaluate_opinion_batch` when vLLM + llm_evaluation.
- Keep fallback to single-call path.
6. **Testing**
- Unit: config validation, pool attach logic, compatibility checks.
- Integration: 2+ experiments, same pool, parallel clients, restart scenarios.
- Load: throughput/latency under concurrent experiments.
7. **Rollout**
- Feature flag for shared pools.
- Start with admin-only; then open to researchers if needed.

## Practical next decision
If you want a low-risk first step, implement only:
- pool selector + namespace-aware reuse + strict validation,
keeping opinion dynamics batching unchanged.

Then do opinion batching as Phase 2 to improve quality/performance once shared pool stability is validated.
