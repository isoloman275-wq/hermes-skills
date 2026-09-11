---
name: hermes-crash-breaker
description: Circuit breaker for Hermes kanban worker crash loops. Detects repeated
  task failures, auto-blocks the card, downgrades the model, and alerts via the
  gateway. Use whenever kanban auto-dispatch is ON (always in this lab).
triggers: [kanban dispatch, task failure, worker crash, OOM, silent_death]
requires: [hermes-kanban-fleet, model-routing]
---

## Context
This lab runs `hermes kanban` auto-dispatch ON with no circuit breaker. Two real
incidents proved the gap: t_f4d9bbe9 hard-looped ~50x on a missing skill until
manually archived; t_76c45f57 died silently (no failure event) on an OOM/handshake
crash. A breaker prevents both: it blocks runaway cards and surfaces a diagnosis
instead of burning M2 cycles or dying quietly.

## Verified anchors (this lab)
- Kanban CLI: `hermes kanban` — subcommands: list, log <id>, diag, stats, reclaim,
  archive, gateway, profiles.
- Failure signal: `hermes kanban log <card_id> 2>&1 | grep -c "Error:"`.
- Ollama endpoints: M1 <lab-node-16>:11434, M2 <lab-node-15>:11434, M3 <lab-node-13>:11434.
  Resident models: `curl -s http://<ip>:11434/api/ps`.
- Models (routing tiers — AUTHORITATIVE 2026-07-30):
  qwen3.8:27b-132k (thinking model, M2 ONLY; gemma4 + dup qwen3.8:27b-132k removed; == qwen3.8:27b-132k
  same weights; 256K ctx). NO ornith:35b / "hermes-35b" exists (any skill citing it is WRONG).
  architect→qwen3.8:27b-132k (M2); coder→OpenRouter tencent/hy3 (cloud, off-M2); researcher/reviewer→
  qwen3.8:27b-132k (M2); builder/data-analyst→ornith:9b (M1); copywriter/devops/ip-guard→qwen3.5:4b (M3);
  qwen3.5:2b (M3 aux).
- All 9 profiles set `delegation.reasoning_effort: none` (thinking OFF) — done 2026-07-30 (user prefers
  system-wide fixes).

## Steps
1. On every task failure, record an incident: (card_id, ts, error_class ∈ {missing_skill, oom, tool_handshake, timeout, silent_death, protocol_violation, other}. Persist to fact_store as entity type `incident` trust 1.0 if running in-agent.
2. Pre-re-dispatch, count failures for card_id in the last 15 min.
3. Thresholds:
   - error_class = missing_skill → BLOCK IMMEDIATELY. Never retry (can never succeed;
     this is the t_f4d9bbe9 pattern).
   - error_class = protocol_violation → **ARCHIVE IMMEDIATELY, do not retry.** This is the
     t_711f9a89 / t_76c45f57 pattern (2026-08-05): a worker spawned by auto-dispatch exits cleanly
     (rc=0) WITHOUT calling `kanban_complete` or `kanban_block`, so the dispatcher counts
     each as a crash and RE-DISPATCHES — producing a never-ending ~60s loop (4300+ runs
     in this incident) that churns M2/cloud cycles and floods the task_events log. Retry
     can never succeed because the worker has no bug to fix in its work — it's the worker
     harness failing to signal completion. Fix = `hermes kanban archive <id>` (or
     `block` then `archive`; note `block --reason` is NOT a valid flag). Kill any stray
     claiming process (`pgrep -af <task_id>`), and verify the board list is clean. This is
     the #1 reason a kanban task shows `running` indefinitely with zero progress — the
     dispatcher is re-spawning it in a loop, not that the task is legitimately long.
   - 2 failures, same error_class → RETRY ONCE on a smaller/off-machine model.
     Reality 2026-07-30: M2 is hermes-ONLY (no smaller local model), so a qwen3.8:27b-132k
     OOM can't be downgraded in-place — REASSIGN the card to ornith:9b (M1, builder) or
     coder=hy3 (cloud, off-M2) instead. Changing a profile's model is a CONFIG change →
     if kanban supports a per-task model override, use it; otherwise ALERT for human
     sign-off (do not silently edit profile config — HARD RULE).
   - 3 failures, any class → set card status BLOCKED, write failure summary into the
     card, send gateway alert (Telegram) with card_id + last error.
   - error_class = oom from an M2 model → also `curl -s http://<lab-node-15>:11434/api/ps`;
     if >1 large model resident, recommend unloading extras before retry (see
     ollama-fit-optimizer).
4. Heartbeat guard for silent deaths: a worker must touch its card every 120s;
   a missed heartbeat = synthetic failure error_class=silent_death (t_76c45f57 pattern).
5. Reset failure counters on card edit/re-scope, NOT on retry.

## Pitfalls
- A task stuck `running` with zero progress is often a protocol_violation LOOP (worker exits
  rc=0 without complete/block, dispatcher re-spawns forever), NOT a long job — check
  `hermes kanban show <id>` for a long run-count of "protocol_violation" and archive it.
- **Run-count scale (2026-08-05):** t_76c45f57 alone reached **8,642 recorded runs / 41,470
  events** over 2.5 weeks with ZERO output — all protocol_violation or "pid not alive".
  A "running for weeks" card is almost always this loop, not a legitimate long task. The
  dispatcher keeps re-spawning every ~60s even after the underlying feature is deprecated
  to backlog — the card itself must be archived (any card type, incl. feature cards, not just
  debug ones). Reassure/verify with the user before archive if it's a real feature card, but
  expect "if it does nothing, delete it" is usually the answer.
- `hermes kanban block --reason "..."` FAILS (`unrecognized arguments: --reason`) — block
  takes no reason flag; just `block <id>` then `archive <id>`, or archive directly.
- Silent deaths emit NO failure event — the heartbeat synthetic-failure is mandatory.
- Never downgrade architect below hermes-9b (architecture on a 4b is confidently wrong).
- Do not turn auto-dispatch OFF — the breaker replaces the need for that blunt fix.
- Log every breaker action to fact_store so weekly incident synthesis can update skills.
- M2 is now hermes-ONLY (no smaller local model). A qwen3.8:27b-132k OOM on M2 cannot be
  downgraded in-place — REASSIGN the card to ornith:9b (M1, builder) or coder=hy3 (cloud,
  off-M2) instead of stepping down a (non-existent) smaller M2 model. (S4/t_76c45f57 recovered
  this way 2026-07-30: it had blocked on an M2 OOM; unblocked onto coder/hy3 it ran off-M2.)
- UNBLOCK + REDISPATCH: `hermes kanban unblock <id>` releases a blocked card and the gateway
  auto-dispatches it. Reassign to a cloud-capable profile first to run it off a constrained machine.
- DATA FRESHNESS: all worker searches must use the live current date (enforced via
  ~/.hermes/SOUL.md, injected into every session). Include year/date in queries; never hardcode
  stale dates.
