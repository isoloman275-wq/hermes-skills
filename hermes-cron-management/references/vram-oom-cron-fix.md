# Agent cron VRAM-OOM → no_agent fix — worked example

## Situation
`Lab Health Check Daily` cron (`<job-id>`) — an AGENT job using local model
`<your-model> served by Ollama on M2 (<lab-host>:11434), schedule `every 1440m`,
deliver `local`. It ran fine for weeks, then started erroring daily from 2026-08-05.

## Error (both Aug 5 and Aug 6 runs)
```
RuntimeError: HTTP 500: llama-server process has terminated: exit status 1: cudaMalloc failed: out of memory
alloc_tensor_range: failed to allocate CUDA0 buffer of size 1666240512
error loading model: unable to allocate CUDA0 buffer
```
(Aug 5 buffer size was 1188747264; Aug 6 was 1666240512 — size varies with the model's current target load.)

## Diagnosis
- The script the cron invokes (`/<home>/.hermes/scripts/lab-health-check.sh`) is a
  deterministic shell health check — it needs NO LLM.
- The cron is an agent job, so it loads the model to run the agent loop. M2 GPUs were
  near-saturated; live read at fix time: GPU 0 = 11146/12288 MiB (90%), GPU 1 = 11555/12288
  (94%) → only ~765 MiB / 358 MiB free → Ollama can't allocate a CUDA buffer → HTTP 500.
- Not a provider/base_url 400 error, not a silent skip. The script was never the problem.

## Fix
`cronjob action=update job_id=<job-id> no_agent=true prompt="" script="lab-health-check.sh"`
- Result persisted correctly: `no_agent: true`, `script: lab-health-check.sh`, schedule
  `every 1440m` unchanged, `deliver: local` unchanged, `model` left in place (ignored by no_agent).
- Note the skill's existing rule held: `script` must be the BARE FILENAME relative to
  `~/.hermes/scripts/`, and `prompt` must be cleared to `""`.

## Verification
`cronjob action=run job_id=<job-id>` → async fired. New output file appeared:
`~/.hermes/cron/output/<job-id>/2026-08-07_01-27-53.md` headed
`Mode: no_agent (script)` with the full clean health report:
```
LAB HEALTH CHECK 2026-08-07
M1 Orchestrator   CPU Load: 0.00 ... Memory: 1.8Gi/23Gi ... Disk: 927G free
M2 @ .15          GPU 0: 90% used ... GPU 1: 94% used ... Ollama API: OK
M3 @ .13          SSH: OK (DESKTOP-1J18NTG)
Done 2026-08-07T01:27+12:00
```
No OOM error → fixed.

## Lab follow-up (surfaced to user)
M2 VRAM genuinely near-capacity (90–94%, <1 GiB free per GPU). Stable temps (41–49°C).
The cron fix removed one load source; if any future workload needs a large model on M2,
free a slot first (`ollama-model-vram-setup` / `check-m2-vram` skills).
