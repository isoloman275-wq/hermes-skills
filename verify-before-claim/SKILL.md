---
name: verify-before-claim
description: Tool-proof every factual claim this turn or call unverified. Includes live enforcement engine.
version: 2026-08-24
author: NZ1Labs (Hux / Hermes)
setup_needed: true
setup_skipped: false
---

# Verify-Before-Claim (Hux's trust rule — now enforced at runtime)

Hux has caught Hermes stating unverified "facts" repeatedly — asserting a
process is dead, a file missing, M2 free, a balance — from partial probes or
stale memory. That is the #1 trust-destroyer. This skill makes the standard
explicit, checkable, and **enforced by code**.

## THE RULE (non-negotiable)

Before outputting ANY claim about:
- a process/service/training job being alive/dead/running
- a file/dir/checkpoint/model existing or not
- GPU/VRAM/util on any node
- a dollar amount/balance/payout/reward
- whether M2/M1/M3 is free or has something resident

you MUST have executed the verifying tool call **IN THE SAME TURN** and the
claim must match what it returned. If you have NOT run the check, phrase it as
"I haven't checked" / "I don't know yet, checking" — NEVER as a finished fact.

## Enforcement Engine

This skill ships a live enforcement module: `verify_guard.py`

```
 ~/.hermes/skills/devops/verify-before-claim/
 ├── SKILL.md              ← you are here
 └── verify_guard.py       ← the enforcement engine
```

### Usage from Python
```python
from verify_guard import guard
result = guard(response_text="M2 is free and qwen3.8 is not loaded")
print(result.verdict)     # "PASS" | "FAIL" | "UNVERIFIED" | "CLEAN"
print(result.probes)      # List[ProbeResult] with evidence
print(result.blocked_text) # Response with failed claims redacted
```

### Usage from CLI
```bash
# Run all probes against live lab
python3 verify_guard.py --probe-only

# Check a specific response text
python3 verify_guard.py --check-text "M2 is free, training is dead" --json

# Self-test (connects to M2/M3, checks everything)
python3 verify_guard.py --self-test
```

### What it detects and probes

| Claim Pattern | Category | Probe Used | Severity |
|---|---|---|---|
| `M2 is free/busy/running` | process | SSH→ps + nvidia-smi + Ollama API | critical |
| `M3 is free/busy/running` | process | curl M3:11434/api/ps | critical |
| `qwen3.8 is loaded/not loaded` | ollama_model | curl :11434/api/ps (M2+M3) | high |
| `ComfyUI is up/down` | process | curl :8188/queue | high |
| `training is dead/done/running` | training | SSH→ps aux | high |
| `TikTok not posting` | process | wmic + content_history.json | high |
| `GPU at X% / VRAM full` | gpu | nvidia-smi via SSH | high |
| `file X exists/missing` | file | os.path.exists | medium |
| `disk is full/empty` | disk | os.statvfs | medium |
| `no posts/renders today` | process | regex match, flagged for probe | high |

### Output

```
Verdict: FAIL
Claims: ['M2 is free', 'qwen3.8 is not loaded', 'ComfyUI is running']

  [✓ VERIFIED] M2 state → GPU active, Ollama: qwen3.8:27b-132k
  [✗ FAILED]   qwen3.8 not loaded → actually loaded on M2
  [✗ FAILED]   ComfyUI running → unreachable on localhost:8188
```

## FORBIDDEN (these are lies, not mistakes)

- "M2 is free" / "the run is dead" without `/api/ps` + `nvidia-smi` + `ps aux`
  in the same turn. Run-state proof = ALL THREE.
- "no venv exists" / "that file isn't there" from checking ONE path only.
  An empty probe = "not found at THIS place", NEVER "doesn't exist".
- Any status claim from memory/a previous session without a fresh live re-check.
- Concluding a verdict from a buggy or partial measurement.
- Reporting a pulled repo as "staged" without `ls` proving runnable code.

## Enforcement Policy

1. About to state a fact? Did I run the proving tool THIS turn? If no → run it
   first, or say "haven't checked".
2. Batch independent verification (terminal/ssh/curl) into one turn.
3. After user correction → FIRST re-verify from live source, not apology.
4. Acknowledge AND execute the fix in the same turn. A promise with no tool
   result = a lie.

## Wire into agent responses

Wired as a `post_tool_call` hook in `~/.hermes/config.yaml` (line 440):

```yaml
hooks:
  post_tool_call:
    - command: <home>/.hermes/hermes-agent/venv/bin/python3 <home>/.hermes/skills/devops/verify-before-claim/verify_guard_hook.py
      description: "Verify-before-claim enforcement on tool results"
      fail_closed: false
      timeout: 60
```

Or use inline at the top of any skill's SKILL.md instructions:
```
Before responding, call the verify_guard engine to check your answer
for factual claims about lab state. If any claim fails verification,
redact it and note what was actually found.
```

## References
- `references/verified-claims.md` — Log of probe results per session (append after each significant lab action)
- `references/qa_pairs.json` — FAQ covering negation logic, crash causes, and cross-machine probing
- `ultron-execution-discipline` — Parent discipline (RULE 14 now links here)
- `evidence-before-claim` — Original rule doc (now superseded by this engine)

## Known Bugs Fixed (2026-08-24)
| Bug | Symptom | Root Cause | Fix |
|---|---|---|---|
| Negation not inverted | `"qwen3.5 is NOT loaded"` marked FAIL when probe confirmed absent | Phase 3 used same predicate for positive and negated claims | Negated claims now use `any(not p.verified for p in relevant_probes)` |
| `UnboundLocalError` when `run_probes=False` | `guard(text, run_probes=False)` crashed on first claim | `verified_claims`, `failed_claims` initialized only inside `if run_probes:` block | Moved initialization to top of `guard()`, before the conditional |

## Session-proven additions (2026-08-27)

- **Approval-mode interference (user-felt as "needing permission for every step")**: root
  cause was `approvals.mode: manual` in config — EVERY flagged shell command prompted the user,
  derailing flow mid-exploit. Fix applied live: `hermes config set approvals.mode smart`
  (auto-runs low-risk, prompts only on genuinely destructive). When a user says "stop asking me
  for permission", check THIS setting before assuming it's prompt-phrasing; verify with
  `hermes config get approvals.mode` and report before/after values in the same turn.
- **Timeout-180s corollary**: long jobs (build runs, waits >90s) must be structured
  launch-now + read-back-later, writing state to disk between calls, OR run
  `terminal(background=true)` — never sleep-poll inside one foreground call.
- **Standing Telegram escalation channel (user-requested)**: no per-step approvals during ops;
  ping via Telegram Bot API only for spawn/reset / flag-submit / irreversible actions
  (credentials from canonical secret registry per Rule 32, chat id verified working 2026-08-27).
  The ping must carry: exact action needed, deadline if any, what to send back.