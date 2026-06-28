# HPC stop propagation and false-completion analysis

## Problem statement

When a running HPC experiment is stopped from YWeb, other running experiments in the same operational context may also terminate. In addition, some clients are later shown as 100% complete even though they were stopped well before reaching their expected duration.

This document traces the relevant code paths in YWeb and the HPC runtime, identifies the likely origin of the issue, and proposes a point-by-point fix plan.

## Relevant code paths

- Manual stop route: `y_web/routes/admin/sub/experiments/_crud.py:2501-2585`
- Backend stop dispatcher: `y_web/src/simulation/execution_backend.py:39-54`
- HPC client shutdown: `y_web/src/hpc/client.py:422-520`
- HPC server shutdown: `y_web/src/hpc/server.py:514-579`
- HPC execution monitor and completion logic: `y_web/src/hpc/log_metrics.py:431-725`
- HPC log-driven auto-stop path: `y_web/src/hpc/log_parser.py:580-666`
- Schedule group stop/progression: `y_web/routes/admin/sub/experiments/_schedule.py:700-920`
- Schedule background monitor: `y_web/src/experiment/schedule_monitor.py:1-90`
- Ray namespace and orchestrator setup: `external/YSimulator/run_server.py:246-248`, `external/YSimulator/run_server.py:386-443`
- Ray client deregistration uses bare client name: `y_web/src/hpc/client.py:472-497`, `external/YSimulator/YSimulator/YClient/client.py:1464-1465`

## What is directly confirmed

### 1. The manual stop route itself is scoped to one experiment

`stop_experiment(uid)` only queries `Client.query.filter_by(id_exp=uid)` and `Exps.query.filter_by(idexp=uid)`. It does not directly iterate over sibling experiments.

That means the cross-experiment effect is not caused by the top-level route looping over all experiments.

### 2. The backend stop path is shared and includes extra side effects

`stop_server_for_experiment()` calls `stop_all_adhoc_clients(experiment, pause=False)` before stopping the server in both standard and HPC flows.

For HPC specifically, `stop_client_for_experiment()` delegates to `stop_hpc_client()`, which:

- resolves the experiment folder,
- connects to Ray using the namespace found in `ray_namespace.temp` or the default `social_sim`,
- deregisters the client from the `Orchestrator` actor using only `cli.name`,
- then kills the process tree and clears the stored PID.

This is important because the stop sequence is not just a local PID kill. It also mutates shared Ray state.

### 3. The HPC monitor treats shutdown as completion

The monitor loop in `y_web/src/hpc/log_metrics.py` does two things that matter here:

- `check_hpc_client_execution_completion()` returns `True` if the last line of the execution log is exactly `"Client shutdown complete"`.
- `mark_hpc_client_as_completed()` then forces:
  - `client_exec.elapsed_time = client_exec.expected_duration_rounds`
  - `client.status = 0`

So a client that is stopped manually can be reclassified as "completed" solely because it shut down cleanly.

### 4. Experiment completion is inferred from stopped clients plus elapsed time

`check_and_terminate_hpc_experiment()` considers a stopped client to be truly completed when:

- `client.status == 0`, and
- `client_exec.elapsed_time >= client_exec.expected_duration_rounds`

If all clients are stopped and at least one is truly completed, the experiment is marked:

- `exp.running = 0`
- `exp.exp_status = "completed"`

This makes the UI show the experiment as fully complete, even if it was manually interrupted.

### 5. The schedule layer can fan out the effect

The schedule monitor periodically calls `_do_check_schedule_progress()` in a background thread.

That function:

- treats a group as complete only when every experiment in the group has `exp_status == "completed"`,
- then stops every running experiment in the current group,
- then advances to the next group.

If the HPC monitor or log parser incorrectly promotes a stopped experiment to `completed`, the schedule layer can then treat the current group as finished and tear down the rest of the group.

## Likely origin of the issue

The observed behavior is most likely the result of two coupled problems:

### A. Manual stop and natural completion are not distinguished

The current code path uses the same terminal state for:

- an experiment that naturally ran to the end, and
- an experiment that was manually stopped but produced a normal shutdown log line.

Because the monitor only checks the shutdown message and then forces elapsed time to the expected duration, a manual stop can become indistinguishable from a real completion.

That explains the "100% execution" symptom.

### B. Ray/orchestrator shutdown is scoped too loosely for cloned experiments

`stop_hpc_client()` deregisters a client from the `Orchestrator` actor using only the client name:

- namespace comes from `ray_namespace.temp` or falls back to `social_sim`,
- `deregister_client(cli.name)` has no experiment-scoped identifier.

If multiple cloned experiments share the same Ray namespace and reuse the same client names, a stop in one experiment can deregister a live client in another experiment. This is especially plausible for copies of the same experiment, where the client names are often identical.

This is the most likely explanation for "stopping one experiment terminates other running experiments".

## Why the current design is fragile

- The manual stop route, the HPC log monitor, and the schedule monitor all act on the same `Exps`, `Client`, and `Client_Execution` records, but they do not use a separate terminal-state model.
- A single `status = 0` means both "manually stopped" and "naturally completed".
- The monitor rewrites execution progress to the expected duration on shutdown, which destroys the evidence of partial completion.
- Ray deregistration uses a shared namespace and a non-unique client identifier.
- Schedule progression is based on `exp_status`, so once a stopped experiment is mislabeled as completed, group-level automation can cascade to sibling experiments.

## Point-by-point fix plan

### 1. Split "stopped" from "completed"

Introduce an explicit completion model for HPC clients and experiments.

Recommended shape:

- keep `status` for running/stopped,
- add a completion flag or terminal reason field, for example:
  - `completed_by_monitor`
  - `stop_reason`
  - `terminal_state`

Then:

- manual stop sets `status = 0` and `stop_reason = "manual_stop"`,
- natural completion sets `status = 0` and `stop_reason = "completed"`,
- the UI should only show 100% when the terminal state is truly completed.

### 2. Stop overwriting elapsed progress on manual stop

`mark_hpc_client_as_completed()` should not be used for manual shutdown paths.

For manually stopped clients:

- preserve the last observed `elapsed_time`,
- preserve the last observed `last_active_day` and `last_active_hour`,
- do not force them to the expected duration.

That keeps the post-stop UI honest and prevents false 100% completion.

### 3. Make completion detection require an explicit completion signal

`check_hpc_client_execution_completion()` currently treats `"Client shutdown complete"` as sufficient proof of completion.

Replace that with one of the following:

- a distinct log marker emitted only by natural simulation completion,
- or a structured completion field in the state/log payload,
- or a final round check that confirms the client actually reached its expected duration before shutdown.

In other words, shutdown alone should not imply completion.

### 4. Scope Ray deregistration to the experiment

Change the orchestrator contract so that deregistration is keyed by experiment and client, not by client name alone.

Options:

- pass a composite key such as `{experiment_id}:{client_id}`,
- or register each client under an experiment-prefixed name,
- or use an experiment-specific namespace that is guaranteed unique and enforced by the server.

This removes the risk that a stop in one cloned experiment unregisters a client in another cloned experiment.

### 5. Protect schedule group logic from false completion

Before `_do_check_schedule_progress()` advances or stops a group, it should validate that each experiment is truly complete, not merely stopped.

Recommended checks:

- experiment terminal state is explicit,
- all clients are truly completed,
- no client is in a manual-stop state.

This prevents one manually stopped experiment from making the whole group look finished.

### 6. Add regression tests

The fix should be covered by tests for at least these cases:

- stopping one running HPC experiment does not stop sibling experiments in the same group,
- a manual stop below the expected duration leaves the experiment in `stopped` state, not `completed`,
- a manually stopped client does not get its elapsed time rewritten to 100%,
- schedule progression does not advance when a group contains manually stopped but incomplete experiments,
- Ray deregistration is isolated to the targeted experiment/client pair.

## Expected outcome after the fix

- Manual stop affects only the targeted experiment.
- Running sibling experiments continue uninterrupted.
- A stopped experiment remains visibly stopped, not falsely completed.
- Schedule/group automation advances only on real completion.
- Cloned experiments can coexist safely even when they reuse client names.

## Conclusion

The issue is not in the top-level stop route alone. It is caused by a combination of:

- shutdown being treated as completion,
- progress being overwritten to 100% on shutdown,
- group automation trusting that completion state,
- and Ray deregistration being keyed too broadly for cloned experiments.

The safest fix is to separate manual stop from natural completion, preserve partial progress, and scope Ray/orchestrator state to the experiment instance.
