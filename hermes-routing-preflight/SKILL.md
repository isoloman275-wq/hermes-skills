> Published from NZ1Labs internal tooling. Private LAN details and model names
> replaced with `<lab-host>` / `<your-model>` placeholders.

---
name: hermes-routing-preflight
description: Validates profile->model->machine->ctx assignment before any subagent or
  kanban dispatch. Catches config drift (e.g., a profile on the wrong model) and
  context-overflow before it becomes a crash loop. Single source of truth = routing table.
triggers: [subagent dispatch, kanban dispatch, profile config change, session start]
requires: [hermes-profile-config, model-routing, ollama-fit-optimizer]
---

## Context
Config drift is real: a profile can point at a model that isn't installed or isn't
resident on its target machine. Preflight validates profile<->model<->machine<->ctx
before dispatch, so silent drift is caught before it becomes a crash loop.

The methodology here is generic — substitute your own model inventory, machine
roles, and routing table.

## Build a routing table first (single source of truth)
- Pull the ACTUAL inventory via `GET /api/tags` on every machine plus `/api/ps` for
  residency. Never trust a cached or externally-audited table — verify against live
  state, because audits routinely assume models that don't exist or treat a cloned
  model and its source as two distinct models.
- Record, per machine (`<lab-host>`), the models present, their context size, and
  which are resident/warm vs cold.
- Record, per profile, the model + machine it is assigned to.
- Keep that table authoritative; preflight diffs the live state against it.

## Pre-dispatch checks
a. Profile's configured model == routing-table model (drift check).
b. Estimated prompt tokens + expected output < model ctx limit with 15% headroom.
   Estimate tokens from chars: use chars/3.5 (code + dense non-Latin scripts tokenize
   denser than plain English), not chars/4.
c. `reasoning_effort == none` for all delegation calls (regression guard on the
   "thinking-model-as-worker" fix — a thinking model emits reasoning tokens that break
   the tool handshake).
d. Target Ollama endpoint responds to `/api/ps` within 3s.

## Actions
- **On drift:** BLOCK dispatch, report expected-vs-actual, require explicit human
  override. NEVER silently "fix" a profile config (config change = sign-off).
- **On ctx overflow:** chunk the task, or route to a larger-context resident model.
- `/api/ps` timeout on a WSL host can false-positive during Windows sleep; retry once
  before declaring the endpoint down.

## Pitfalls

- **VRAM residency:** enforce max 1 large model warm at a time per inference host
  (serial dispatch for cards on the same machine). Concurrent large models on one
  GPU host = OOM.
- **Ground truth before external audit:** when an AI review proposes routing changes,
  pull the ACTUAL model inventory first (`/api/tags` + `/api/ps`). Audits routinely
  assume models that don't exist or treat a cloned model and its source as distinct.
  Ground every decision in live state, then come back for sign-off before changing
  anything.
- **High-IP-sensitivity roles** should always be routed to a larger/more capable model;
  a small aux model is a risk for privileged decisions.