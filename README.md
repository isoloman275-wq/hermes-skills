# hermes-skills

A curated, **scrubbed** set of proven [Hermes Agent](https://github.com/NousResearch/Hermes-Agent)
skills for running a multi-machine AI homelab and its autonomous fleets. Private
topology has been replaced with placeholders (`<lab-host>`, `<home>`) so you can
drop these into your own setup.

## Skills

- `lab-health/` — full homelab health check (reachability, Ollama models, GPU/VRAM, services).
- `check-m2-vram/` — quick VRAM + loaded-model check for a GPU node.
- `hermes-routing-preflight/` — validates profile→model→machine→context before a run.
- `m1-ollama-watchdog/` — self-healing Ollama liveness watchdog (relaunches a silently-dead server so dependent fleets don't stall).
- `fleet-calibration/` — measure kanban worker accuracy (PASS / faked-done / crash) via deterministic marker-file tasks.
- `board-drain-watcher/` — wait for a kanban board to clear before running a follow-up step.
- `hermes-cron-management/` — diagnose & repair Hermes cron jobs (400 model-ID trap, silent-skip, agent-cron OOM).
- `shipping-security-gate/` — security-threats layer to run before shipping any app, site, or public code.
- `agent-verification-harness/` — independent-verifier bench + fleet verification gate: prove a worker model actually did the work (measured A/B/C: an independent verifier catches blind-spot errors every run; self-critique adds zero).
- `hermes-desktop-wsl/` — run and debug the Hermes desktop app from WSL/WSLg: renderer-crash triage, window-recovery sequence, launcher discipline, plus working desktop-plugin templates.
- `verify-before-claim/` — enforcement layer that blocks unverified factual claims before they ship: every status statement must be tool-proven in the same turn.

Each folder is a drop-in Hermes skill (`SKILL.md`, plus any helper script it ships).

Built by NZ1Labs.

- `ultron-execution-discipline/` — the operating standard this lab runs on: execute-don't-narrate, verify the deliverable (not the code claiming success), explicit-OK gates for irreversible actions, veto = hard cancel.
- `verify-before-claim/` — enforcement engine that scans outgoing responses for factual claims and probes them live (GPU/process/file/balance) before delivery.
- `evidence-before-claim/` — proof precedes every claim in the same turn; empty probe ≠ nonexistence; verification trio before declaring anything dead/alive.
- `watchers/` — poll RSS/JSON/GitHub feeds with watermark dedup for change alerting.
- `hermes-process-reaper/` — prevents and cleans up stale/duplicate background processes and wedged watchers.
- `hermes-crash-breaker/` — circuit breaker for kanban worker crash loops (model↔provider mispair root cause).
- `automation-health-monitoring/` — proactive watchdogs for unattended automations: verify the OUTPUT fired, not that the flag says ok.
- `kanban-worker/` — pitfalls, examples, and edge cases for Hermes Kanban workers.
- `hermes-outbound-webhooks/` — HMAC-signed lifecycle event push from Hermes to external endpoints.
- `webhook-subscriptions/` — event-driven agent runs triggered by external webhooks.
- `session-recovery/` — resume a crashed/interrupted Hermes session by reconstructing state from history + workspace.
- `systematic-debugging/` — 4-phase root-cause debugging: understand the bug before fixing it.
