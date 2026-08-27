---
name: agent-verification-harness
description: Use when improving agent reliability; wire verifier swarms.
---

# Agent Verification Harness (independent verifier > self-critique)

## The measured result (lab bench, 2026-08-24, deterministic oracle)

A/B/C benchmark on 10 verifiable tasks, graded by a Python oracle (no LLM grading bias):

| Condition | Accuracy | Latency | Verdict |
|---|---|---|---|
| A: bare cheap model (<your-model> @ M3) | 9-10/10 | ~190s | baseline |
| B: worker + self-critique ("check your own answer") | 9-10/10 | ~2x | **zero gain — dead pattern** |
| C: worker + INDEPENDENT verifier (<your-model> @ M1) | 9/10 | ~2x | **caught the blind-spot error every run** |

Key finding (reproduced 3 runs): on t05 (list primes < 20), the worker dropped "19".
Self-critique REPEATED its own error both times it occurred. The independent
verifier (different model, different machine) corrected it EVERY time it ran.
This reproduces the published "observer independence is decisive" finding on our
own hardware. Full data: `hermes-workspace/verify-bench/{verify_bench.py,RESULTS.md}`.

RULE OF THUMB: cheap model + independent verifier ≥ expensive model accuracy,
at commodity cost — but only with a healthy harness underneath.

## Bench recipe (rerunnable)

1. Write N tasks with DETERMINISTIC oracles (`lambda answer: "391" in answer`), never LLM grading.
2. Condition A: single generate call. Condition B: generate with "think step by step, output FINAL:" then grade the final line. Condition C: generate as in B, then send task+proposed-answer to a DIFFERENT model on a DIFFERENT machine ("strict verifier; reply FINAL: <corrected answer>").
3. Grade all three conditions against the same oracles. Report pass-rate AND wall-time.
Script: `hermes-workspace/verify-bench/verify_bench.py` (hosts/model names at top).

## Wiring into Hermes kanban (done 2026-08-24)

`hermes kanban swarm --worker 'profile:title' --verifier independent-verifier --synthesizer <profile> '<goal>'`
- `~/.hermes/profiles/independent-verifier/` = <your-model> @ ollama-m1, with an AGENT.md
  adversarial protocol: verify acceptance criteria line-by-line WITH TOOLS; claims without
  tool evidence are UNVERIFIED=FAIL; PASS only via kanban_complete metadata `{"gate":"pass"}`;
  FAIL via block with a numbered defect list. Judge, don't improve.
- The swarm's auto-generated verifier card gates completion — good enough; the AGENT.md adds
  the adversarial posture.

### CRITICAL PITFALL — provider fallback silently violates machine bans (hit first wiring test)
Worker profiles carry fallback providers (builder: primary ollama-m1, FALLBACK ollama-m2).
When primary is slow/wedged, the runtime silently routed to <your-model> ON M2 → OOM crash-loop
×12 and unauthorized load on a machine the user had banned that day. Checks before ANY dispatch:
1. Grep assignee profile config.yaml fallback chains vs current user machine-access rules;
   strip banned hosts (with user approval — profiles are his).
2. Pin hard cases per-task: `hermes kanban set-model <task_id> <model> <provider>`.
3. After spawn, READ THE FIRST LOG LINES for the resolved base_url — config alone lies.
4. Emergency stop when it hits a banned host: reclaim + archive ALL swarm cards (worker,
   verifier, synthesizer — archive fails while running, so reclaim first), kill orphaned PIDs,
   verify zero worker processes remain. M2 was unharmed (requests rejected, never allocated).

## Verifier model sizing (user-set lab convention)

- Agent-grade models cap context at ~64K minimum-viable (Hermes' tool-use floor), NOT native
  max — balanced KV load, fewer wedges. M1: `<your-model> M3 ships num_ctx 64000 already.
- Sub-64K variants (e.g. `<your-model> @ 8K) are SPECIAL-PURPOSE ONLY (tiny prompts,
  raw API callers) and can NEVER be a Hermes profile model — the 64K gate refuses them.
- Create via `/api/create` with a `parameters` dict (NOT a raw modelfile string):
  `{"model":"<your-model>

## Related wedge lesson (M1 Windows Ollama reload-loop)

Verifier timeouts during the bench were NOT VRAM starvation: timed-out jobs sat in Ollama's
request queue and re-requested the model after each llama-server kill → reload-loop at 128K ctx
on an 8GB card. Fix: kill serve+llama-server processes (PowerShell Stop-Process), relaunch serve
(wipes queue), load the capped variant FIRST. Post-fix: 44.5 tok/s, ~2.3s/verification.

## What NOT to do

- Do not use self-critique as a quality mechanism — measured dead weight.
- Do not trust profile configs for machine routing — verify the resolved endpoint per run.
- Do not put a sub-64K-context model on any Hermes profile.
- Do not run the bench with LLM grading — oracle must be deterministic or the comparison is noise.
