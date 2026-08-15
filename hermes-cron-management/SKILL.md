---
name: hermes-cron-management
description: "Diagnose and repair Hermes cron jobs. Three failure classes - (1) model-ID errors / wrong provider/base_url (a local Ollama model name sent to a remote provider -> 400 'not a valid model ID'); (2) silent skips where a cron misses its slot with NO error because the gateway process wasn't running; (3) agent-cron OOM on the inference host (HTTP 500 / cudaMalloc failed). Covers correct cronjob tool mechanics (base_url must be top-level, not nested), the jobs.json patch fallback, and how to keep the gateway alive."
---

# Hermes Cron Management

## When to use
- A cron reports `last_status: "error"` and the error mentions `not a valid model ID` / HTTP 400.
- You need to repoint one or many crons at a local Ollama instead of the default remote provider.
- Auditing crons for the `provider: null` trap (latent failures that haven't errored yet).
- **A cron "missed" its slot with NO error** — `last_status` still `ok`, but `last_run_at` is stale and `next_run_at` jumped past the missed time. This is the silent-skip failure class (gateway wasn't alive). See "Silent-skip" below.
- **An agent cron reports `last_status: error` with HTTP 500 / `cudaMalloc failed: out of memory`** — the LLM it loads cannot fit in the inference host's VRAM. Fix = convert it to a `no_agent` script job (it almost never needs an LLM).

## Root cause — the "CRON GOTCHA"
`config.yaml`'s default `model.provider: custom` resolves to a remote provider. When a cron is created with `provider: null`, it falls through to that default. If the cron's `model` is a LOCAL Ollama name, the scheduler ships that name to the remote provider, which rejects it:

```
400 - {'error': {'message': '<name> is not a valid model ID', 'code': 400}}
```

This is invisible until the cron actually runs. Jobs that show `last_status: "ok"` but STILL have `provider: null` + a local model name are latent failures — they will 400 on the next run. Fix them proactively, not just the ones already erroring.

## Fix — VERIFIED tool mechanics (read carefully)
The `cronjob` **update** tool does NOT persist `base_url` when it is nested inside the `model` object. It MUST be passed as a separate TOP-LEVEL parameter. Passing it nested silently drops it, leaving `provider: custom` pointing at the remote provider → the cron keeps failing and you think you fixed it.

CORRECT — `base_url` at top level, alongside `model`:
```
cronjob action=update
  job_id:   <id>
  model:    {"model": "<local-model>", "provider": "custom"}
  base_url: "http://<lan-host-ip>:11434/v1"
```

WRONG — `base_url` nested in `model` is silently dropped:
```
cronjob action=update
  job_id: <id>
  model: {"model": "<local-model>", "provider": "custom",
          "base_url": "http://<lan-host-ip>:11434/v1"}   # <- dropped, fix fails
```

### GOTCHA — the cronjob tool + CLI CANNOT set base_url; patch jobs.json
Even with `base_url` passed top-level, `cronjob action=update` may return `No updates provided.` and drop it, and the CLI exposes `--model`/`--provider` but NO `--base-url`. The reliable fallback:

1. Set `model` + `provider` via `hermes cron edit <id> --model <m> --provider custom` (this persists).
2. `base_url` is still `None` afterwards — and with `provider: custom` + no base_url the job falls through to the config default (remote), which rejects local names. You MUST set it.
3. Patch the source of truth directly — back up then JSON-edit `<hermes-home>/cron/jobs.json` for that one job:
   ```python
   import json, shutil, datetime
   p='<hermes-home>/cron/jobs.json'
   shutil.copy(p, p+'.bak_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
   d=json.load(open(p))
   for j in d['jobs']:
       if j.get('id')=='<JOB_ID>':
           j['base_url']='http://<lan-host-ip>:11434/v1'
           j['model']='<local-model>'; j['provider']='custom'
   json.dump(d, open(p,'w'), indent=2, ensure_ascii=False)
   ```
   The scheduler reloads `jobs.json` each tick; `cronjob action=list` reflects it immediately. Keep the change small (one job's routing) and always back up first.

## Silent-skip: gateway not running
If a cron `last_status` is `ok` but `last_run_at` is old and `next_run_at` skipped the missed time, the gateway was down at the slot. The cron registry doesn't record a "didn't run" — it just advances. Fix by ensuring the gateway is alive (check `hermes gateway status` / the service) and that it auto-starts on boot (a scheduled task / systemd unit, with a boot-order dependency on the network so it doesn't start before the LAN is up). Watch for any single-host watchdog that can re-arm it.

## Agent cron OOM on the inference host
If an agent (LLM-driven) cron errors with `HTTP 500` / `cudaMalloc failed` / `unable to allocate CUDA buffer`, its model cannot fit in the host's VRAM (often because a large resident model is already loaded). The fix is usually to **convert it to a `no_agent` script job** (`no_agent: true` + a `script`) so no LLM is loaded at all — a status check or data-collection cron almost never needs an LLM. This avoids the VRAM collision entirely and is cheaper (no tokens).

## Best practice
- Audit the WHOLE cron set at once for `provider: null` + local-model latent failures, not one-by-one.
- A schedule/roster is fictitious if its driver job (orchestrator/watchdog) is itself drifting or skipped — check the driver's last run before trusting the pipeline it schedules.