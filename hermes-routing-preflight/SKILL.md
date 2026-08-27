---
name: hermes-routing-preflight
description: Validates profile->model->machine->ctx assignment before any subagent or
  kanban dispatch. Catches config drift (e.g., architect on wrong model) and
  context-overflow before it becomes a crash loop. Single source of truth = routing table.
triggers: [subagent dispatch, kanban dispatch, profile config change, session start]
requires: [hermes-profile-config, model-routing, ollama-fit-optimizer]
---

## Context
Config drift is real here: a profile can point at a model that isn't installed or isn't
resident on its target machine (e.g. the old 'architect should be on <your-model> assumption
- but NO 35B model exists anywhere; architect is correctly on <your-model> Preflight
validates profile<->model<->machine<->ctx before dispatch, so silent drift is caught.

## ACTUAL lab inventory (verified 2026-07-30 via /api/tags + /api/ps)
- M1 <lab-host>: <your-model> (9B, 256K ctx). NOTHING resident (cold).
- M2 <lab-host>: <your-model> (=<your-model> clone, 27.8B, 256K, thinking/vision/tools) PINNED WARM (~23GB VRAM, keep_alive~infinite); <your-model> (duplicate tag, cold); gemma4:31b-it-qat (30.7B, 256K, vision) = ORPHAN, no profile references it, cold.
- M3 <lab-host>: <your-model> (4.7B, 256K), <your-model> <your-model> NOTHING resident (cold).
- ALL models are 256K context. NO 35B/<your-model> model exists anywhere.
- KEY: <your-model> and <your-model> are the SAME model (cloned copy, thinking off, custom ctx).

## ACTUAL profile -> model assignment (from profile configs, 2026-07-30)
architect/coder/researcher/reviewer -> <your-model> (M2, warm)
builder/data-analyst -> <your-model> (M1, cold)
copywriter/devops/ip-guard -> <your-model> (M3, cold)
aux tool-call -> <your-model> (M3)

## PROPOSED rebalance (EXECUTED 2026-07-30 where noted — do NOT apply remaining autonomously)
- DONE: orphan gemma4:31b-it-qat AND duplicate <your-model> removed from M2 (M2 now hermes-only).
- DONE: coder profile repointed local <your-model> -> OpenRouter <your-cloud-model> (same as main agent). Architect/researcher/reviewer stay on hermes; builder/data-analyst on M1 <your-model> copywriter/devops/ip-guard on M3 4b.
- PENDING user sign-off: S4 (t_76c45f57) retry — now runs on coder/hy3 (off M2), so OOM risk gone; arm crash-breaker on retry.
- No 35B exists, so architect stays on hermes (was never on 35b).

## Pre-dispatch checks
a. profile's configured model == routing table model (drift check).
b. estimated prompt tokens + expected output < model ctx limit with 15% headroom.
   Token estimate from chars: use chars/3.5 (code + te reo Maori tokenize denser
   than English prose), not chars/4.
c. reasoning_effort == none for all delegation calls (regression guard on the
   2026-07-30 fix).
d. Target Ollama endpoint responds to /api/ps within 3s.

## Actions
- On drift: BLOCK dispatch, report expected-vs-actual, require explicit human
  override. NEVER silently "fix" a profile config (HARD RULE: config change = sign-off).
- On ctx overflow: chunk the task (all models are 256K ctx, so rare) or route to a larger-resident model.
- /api/ps timeout on WSL (M1) can false-positive during Windows sleep; retry once
  before declaring the endpoint down.

## Pitfalls
- M2 concurrency: enforce max 1 large model warm at a time (ollama-fit-optimizer +
  serial kanban dispatch for M2 cards). Concurrent large models on M2 = OOM (S4 cause).
- ip-guard on a 4b is a HARD-IP-RULE risk; always escalate FLAG/LOW-CONFIDENCE to 9b.
- VERIFY GROUND TRUTH BEFORE TRUSTING AN EXTERNAL AUDIT: when an AI review (Fable/Opus/etc.) proposes routing or hardware changes, pull the ACTUAL model inventory FIRST — `GET /api/tags` on every machine (M1 <lab-host>, M2 <lab-host>, M3 <lab-host>) plus `/api/ps` for residency. Audits routinely assume models that don't exist (e.g. a '35B/<your-model> that was never installed) or treat a cloned model and its source as two distinct models (<your-model> IS <your-model> — one model). In this lab there is NO 35B anywhere and hermes == 27b. Ground every routing decision in live `api/tags`, not in the review's assumptions. The user explicitly rejected a routing table built on phantom models — verify first, then come back for sign-off before changing anything.
