# Verified Claims Registry

> Auto-generated probe results. Each entry records a factual claim, the
> verification probe that proved or disproved it, and the evidence.
>
> **Rule**: an empty probe = "not found at THIS place" — NEVER "doesn't exist".

## 2026-08-24 — Engine smoke test (post-bugfix validation)

### M2 State (<lab-host>)
| Claim | Probe | Verdict | Evidence |
|---|---|---|---|
| M2 process state | SSH→ps aux + nvidia-smi + Ollama /api/ps | ✓ VERIFIED | No training processes. Ollama: NO_MODELS_LOADED. GPU: 2×RTX3060, ~3% util each, ~3GB VRAM used per card. |
| <your-model> loaded on M2 | curl :11434/api/ps | ✗ FAILED | NOT loaded (model was unloaded for testing). Probe correctly detected absence. |
| ComfyUI running on :8188 | curl :8188/queue | ✗ FAILED | Unreachable from sandbox — likely bound to M2 localhost. Expected in this environment. |

### M3 State (<lab-host>)
| Claim | Probe | Verdict | Evidence |
|---|---|---|---|
| M3 process state | curl :11434/api/ps | ✓ VERIFIED | NO_MODELS_LOADED. Node reachable. |
| <your-model> NOT loaded on M3 | curl :11434/api/ps | ✓ VERIFIED (negation) | Confirmed absent. Negation logic correctly inverted the probe result. |

### Training State
| Claim | Probe | Verdict | Evidence |
|---|---|---|---|
| Training is dead | SSH→ps aux on M2 | ✓ VERIFIED | No training/python processes found on M2. |

### Test Matrix
| Test | Input | Expected Verdict | Actual | Pass? |
|---|---|---|---|---|
| Multi-claim + negation | "<your-model> is not loaded… <your-model> is loaded… ComfyUI is running… Training is dead" | FAIL (<your-model> + ComfyUI wrong) | FAIL | ✓ |
| No claims | "Let me go do some work" | CLEAN | CLEAN | ✓ |
| Negation only (no probes) | "<your-model> is NOT loaded" | UNVERIFIED | UNVERIFIED | ✓ |
| Positive only (no probes) | "<your-model> is loaded on M2" | UNVERIFIED | UNVERIFIED | ✓ |
| Syntax validation | ast.parse(verify_guard.py) | No errors | SYNTAX OK | ✓ |

## 2026-08-21 — Prior baseline (pre-bugfix, partial)
| Claim | Probe | Verdict | Evidence |
|---|---|---|---|
| M2 GPU state | nvidia-smi via SSH | ✓ | 2×RTX3060, GPU0 ~10.6GB/12GB used (ComfyUI render), GPU1 idle |
| M3 Ollama | curl :11434/api/ps | ✓ | Holds <your-model> + <your-model> |
| Te reo base model | ls on M2 /mnt/storage | ✓ | 15GB <your-model> shards present (4 safetensors + config/tokenizer) |

---

**How to use this file:** After any significant lab action, append a new section with date/time + probe results. Reference this file when debugging — it's ground truth for what was verified when. Do NOT use stale entries to override fresh probes; always re-verify before claiming current state.