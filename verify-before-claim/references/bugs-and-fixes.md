# Bugs Found & Fixed During verify-before-claim Build

## Bug 1 — Uninitialized variables when probes disabled (crash)
**File:** `verify_guard.py`, `guard()` function  
**Symptom:** `UnboundLocalError: cannot access local variable 'failed_claims' where it is not associated with a value` when calling `guard(text, run_probes=False)`.  
**Root cause:** `verified_claims`, `failed_claims`, and `claim_verifications` were initialized only inside the `if run_probes:` block. When probes were off, the code fell through to the verdict-building section referencing variables that never existed.  
**Fix:** Moved `claim_verifications`, `verified_claims`, `failed_claims` initialization to the top of `guard()`, outside the `if run_probes:` block. Removed duplicate declarations inside the block.  
**Lesson:** A defensive function should handle all code paths, not just the happy path. Test with `run_probes=False` as well as `True`.

## Bug 2 — Negation detection not inverting per-probe verdicts
**File:** `verify_guard.py`, Phase 3 verdict logic  
**Symptom:** "<your-model> is NOT loaded" was marked FAIL when probes confirmed the model was indeed NOT loaded. The negation flag was detected correctly but never used to invert the verification logic.  
**Root cause:** The original code had identical logic for positive and negated claims — both checked `any(p.verified for p in relevant_probes)`. For a negated claim, the correct check is `any(not p.verified for p in relevant_probes)` (the absence IS the proof).  
**Fix:** Added conditional branch in Phase 3:
```python
if is_negated:
    claim_is_verified = any(not p.verified for p in relevant_probes)
else:
    claim_is_verified = any(p.verified for p in relevant_probes)
```
**Lesson:** Negation is not just a UI label — it flips the entire verification predicate. Test both directions explicitly.

## Bug 3 — Multi-match: only first claim per pattern detected
**File:** `verify_guard.py`, Phase 1 claim scanning  
**Symptom:** Text containing both "<your-model>" and "<your-model>" only detected the first model mentioned.  
**Root cause:** Used `pattern.search()` which returns the first match only.  
**Fix:** Switched to `pattern.finditer()` to iterate over all matches per pattern.  
**Lesson:** When scanning for repeating patterns in text, always use `finditer()` unless you explicitly want only the first hit.

## Bug 4 — PATTERN_GROUPS referenced before assignment (prior session)
**File:** `verify_guard.py`, function `generate_verification_code`  
**Symptom:** Syntax error during import. `PATTERN_GROUPS` was referenced in a function but defined after it in module scope, and the function was called at import time.  
**Root cause:** Module-level code execution order issue.  
**Fix:** Moved `PATTERN_GROUPS` definition to before any function that references it. Ensured no module-level code calls functions that depend on not-yet-defined constants.  
**Lesson:** In Python, module-level execution is top-to-bottom. Constants used by import-time code must be defined before they're referenced.