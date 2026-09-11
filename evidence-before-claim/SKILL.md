---
name: evidence-before-claim
description: Behavioral discipline layer — what humans must do that code cannot enforce.
version: 2026.08.24
author: NZ1Labs (Hux / Hermes)
category: devops
tags:
  - discipline
  - verify
  - halt
  - user-behavior
related_skills:
  - verify-before-claim
---

# Evidence Before Claim — Behavioral Discipline Layer

> This skill covers the **human behavioral rules** that the automated
> `verify-before-claim` enforcement engine cannot enforce. Together they form
> a complete verification system — the engine handles machine-checkable claims,
> this skill governs user-facing judgment calls.

## The Rule

### 1–4. Now Automated → See `verify-before-claim`

Rules 1–4 from the original skill are now enforced at runtime by the
`verify_guard.py` engine:

- **Proof precedes the claim** → engine runs live probes before every response
- **Empty probe ≠ nonexistence** → engine never concludes "doesn't exist" from one probe
- **"Is X safe?" → verify live** → engine always checks process + GPU + models together
- **After user correction → re-verify first** → engine auto-reprobes, not memory

→ **Full engine:** `skills/devops/verify-before-claim/verify_guard.py`

### 5. HALT ON USER VETO (human-only — cannot be automated safely)

When the user vetoes an action:
- **NO** / **stop** / **don't** / **"I don't want that"** / **"not going there"**

You MUST:
1. **Kill it immediately** if running — do not let it finish gracefully
2. **Do NOT re-launch** it, do NOT continue it, do NOT ask to proceed
3. **Stand down completely** until they explicitly say go

> Re-launching after a veto is the single worst offense in this lab.
> Hux has corrected this repeatedly: "launched M1 train after explicit
> 'no', then again — multiple times, each caught"

> NOTE: If the user says a process/layer is "dead weight" or "unused",
> that is NOT authorization to kill it — he means USE IT. Only kill a
> process he explicitly says to remove. When in doubt, restart/keep
> and wire it in instead of pruning.

### Why This Needs a Human Rule

An automated guard can't distinguish "the user wants me to stop THIS
specific action" from "the user wants me to stop all related work."
The context of a veto — whether it's a hard stop, a redirect, or a
conservative pause — requires human interpretation.

## Anti-patterns (never)

- Stating a verdict from a single probe with a too-short timeout
- Confessing to a fault you cannot confirm ("I killed it") without evidence
- Re-asserting a claim after "you didn't verify it" instead of running the check
- Using "no"/"stop" corrections as an excuse to abandon the task entirely

## Cross-references

- `verify-before-claim` — automated enforcement engine
- `ultron-execution-discipline` — execution standards (R2D2 → ULTRON)
- `lab-interaction-rules` — full lab interaction protocol