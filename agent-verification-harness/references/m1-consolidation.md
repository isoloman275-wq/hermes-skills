# M1 Consolidation (2026-08-24, user-directed) — SUPERSEDES variant naming

M1 now carries ONE model: plain `<your-model> with BAKED defaults
num_ctx=65536 + num_gpu=41 (set via /api/create from itself).

- Variants `<your-model> and `<your-model> were DELETED.
- <your-model> (Q5_K_M and Q4_K_M) both DELETED — 17/20 at either quant;
  its failures (letter counting, string reversal, decimal compare) are
  model-level distill blind spots, not VRAM artifacts.
- All profiles reference the single name — including
  independent-verifier's `auxiliary.vision.model`, which is easy to miss.
- Residency proof standard: GET /api/ps must show context_length=65536,
  ~7.41GB of 8GB.

Convention going forward: ONE model name per node with baked defaults; no
suffix variants (-64k/-verifier) that drift from the base. Context
correctness travels with the model via create-time parameters, not
per-request overrides. After ANY consolidation: grep every live profile
config for stale variant names before declaring done.

Earlier sections of SKILL.md that mention `<your-model> as a live model
name are historical — read as `<your-model>
