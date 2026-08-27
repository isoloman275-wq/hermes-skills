# M1 concurrency gauntlet (2026-08-24) — one worker per GPU node

## Setup
5 simple kanban build cards ("write /tmp/m1_gauntlet/task_N.txt containing exactly GAUNTLET-N-PASS")
on builder / <your-model> @ M1. Artifact-on-disk = ground truth.

## Results

| Mode | Outcome |
|---|---|
| Card 1 solo | done ~7 min, byte-exact artifact ✓ |
| Cards 2+3 in parallel (same profile/GPU) | Artifacts written correctly on EVERY attempt, but each worker SIGKILL'd mid-run (~9–16 min) repeatedly — 5+ crash/retry cycles each, never reached kanban_complete under contention |

Ruled out: OOM (host RAM fine, VRAM 7.4GB of 8GB used), fleet watchdog (>90min rule — kills came at 9–16 min), M2 interference (all traffic verified on <wsl-gateway-ip>). Cause: two ~26K-token agent sessions sharing one GPU stretch every API turn to minutes → internal timeouts + reaper wins the race before protocol completion.

## Rule

**A single-GPU node is a QUEUE, not a pool.**
- Cap `max_in_progress_per_profile: 1` for profiles backed by <your-model> / <your-model> local models.
- Swarm sequencing (worker THEN verifier) is naturally serial and safe; never let two cards on the same local model overlap in time.
- Parallel throughput belongs to cloud/M2-class capacity.
- Reliability verdict for <operator>'s profile-handover question: builder/<your-model> EARNED reliability solo (100% artifact correctness, auto-recovery from crashes); it cannot absorb MORE profiles as parallel capacity, only as queued serial work.

## Ops tips learned

- `hermes kanban diagnostics` flags `stranded_in_ready` cards (ready >30 min with no worker) — use it when a board stalls instead of polling show() card-by-card.
- Task-level `kanban set-model --provider X <model>` overrides did NOT survive dispatch retries in practice — profile-config-level routing (stripping unwanted providers/fallbacks from config.yaml) is the only hard guarantee.
- Reclaim-before-archive: archive fails while a task is running; reclaim first, then archive.
- Long inline shell loops with nested quotes can trip the terminal hardline parser — write the loop to a script file or keep loops simple.
