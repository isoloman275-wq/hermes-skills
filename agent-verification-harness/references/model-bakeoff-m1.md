# M1 Model Bake-off + Consolidation (verified 2026-08-24)

## Methodology (reusable)
Serial model comparison on one GPU: identical task battery, deterministic
Python oracle (never LLM-grading), same box, same quant-fit config,
temperature 0.1. Bench scripts live in `hermes-workspace/verify-bench/`
(`model_bench.py <model>` runs 20 verifiable tasks; `verify_bench.py` adds
A/B/C harness conditions).

**CRITICAL — verify residency before claiming results:** check
`GET /api/ps` and read the ACTUAL `context_length` + `size_vram` of the
resident model before each run. A request-level `num_ctx` override silently
masks what the model really loaded (caught: <your-model> "8K" run wasn't testing
its real config; user caught it).

## Measured results (M1 RX 5700XT 8GB)
- <your-model> @64K: **19/20**, ~1.9s/task, 7.4GB resident — CHAMPION
- <your-model> distill Q5_K_M @64K: 17/20, 8.1GB (over-commits 8GB card)
- <your-model> @64K: 17/20 — SAME fails as Q5 → failures are model-level
  blind spots (letter counting, string reversal, decimal compare), NOT
  VRAM artifacts. Quant change doesn't fix capability gaps.
- Different models fail on DIFFERENT tasks → cross-model verifier catches
  what self-models cannot (observer-independence effect).

## Installing a local GGUF into Ollama (the path that works)
1. Download GGUF to disk (curl -L -C - with HF Bearer for resume).
2. Modelfile with FILE PATH source (direct `FROM sha256:<digest>` create
   fails with "pull model manifest: file does not exist"):
   ```
   FROM C:\path\to\model.gguf
   PARAMETER num_ctx 65536
   PARAMETER num_gpu 41
   ```
   Write it WITHOUT CRLF (`printf ... | tr -d '\r'`).
3. Windows side: `ollama.exe create <name> -f <Modelfile>`.
4. Find max num_gpu empirically: test 40 OK / 42 OOM → use 41 (+1 over max
   working layers). Verify fit by loading then reading size_vram vs card.
5. Pin resident during work: `"keep_alive": -1` on first load so nothing
   else claims VRAM.

## Wedge protocol (recurring root cause)
Ollama unload attempts fail because timed-out jobs sit in the request queue
and re-request the model after each llama-server kill → reload-loop at full
context on small cards. Fix: Stop-Process ollama + llama-server together →
restart serve → immediately load the target model keep_alive=-1. Never just
kill llama-server alone.

## Consolidation convention (user preference)
ONE model name per node with baked defaults (num_ctx/num_gpu via create) —
no -64k/-verifier suffix variants to drift. All profiles point at the single
name; context correctness travels with the model, not per-request overrides.
Delete variants after consolidation; grep all live profile configs for stale
names before declaring done.

## Serial vs parallel on 8GB cards
One concurrent agent session works reliably (~7min simple kanban cards);
two sessions share the GPU badly — API turns stretch 3-6x, runs die before
completing their protocol steps. Treat small-VRAM nodes as SERIAL queues:
cap dispatch to 1 worker per node; verifier runs AFTER worker by design so
worker→verifier swarms don't contend.
