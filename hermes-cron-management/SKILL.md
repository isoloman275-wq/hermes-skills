---
name: hermes-cron-management
description: "Diagnose and repair Hermes cron jobs. Two failure classes - (1) model-ID errors / wrong provider/base_url (provider:null to OpenRouter 400 trap, repointing to M2 Ollama); (2) silent skips where a cron misses its slot with NO error because the gateway process was not running (boot-order / auto-start gap). Covers correct cronjob tool mechanics (base_url must be top-level, not nested in model), the silent-skip diagnostic procedure, and how to keep the gateway alive. Trigger when a cron shows last_status error, a 400 not a valid model ID message, provider:null with a local model name, a cron missed/did not run with no error, or when bulk-repointing crons to M2 Ollama."
---

# Hermes Cron Management

## When to use
- A cron reports `last_status: "error"` and the error mentions `not a valid model ID` / HTTP 400.
- You need to repoint one or many crons at a local Ollama (M2) instead of the default OpenRouter provider.
- Auditing crons for the `provider: null` trap (latent failures that haven't errored yet).
- **A cron "missed" its slot with NO error** — `last_status` still `ok`, but `last_run_at` is stale and `next_run_at` jumped past the missed time. This is the silent-skip failure class (gateway wasn't alive). See "Silent-skip: gateway not running" below.
- **An agent cron reports `last_status: error` with an HTTP 500 / `cudaMalloc failed: out of memory` / `unable to allocate CUDA< n> buffer`** — the LLM it loads cannot fit in the inference host's VRAM. Fix = convert it to a `no_agent` script job (it almost never needs an LLM). See "Agent cron OOM on the inference host" below.

## Root cause — the "CRON GOTCHA"
`config.yaml`'s default `model.provider: custom` resolves to OpenRouter (`base_url: openrouter.ai/api/v1`). When a cron is created with `provider: null`, it falls through to that default. If the cron's `model` is a LOCAL Ollama name (e.g. `<your-model> `<your-model> the scheduler ships that name to OpenRouter, which rejects it:

`400 - {'error': {'message': '<name> is not a valid model ID', 'code': 400}}`

This is invisible until the cron actually runs. Jobs that show `last_status: "ok"` but STILL have `provider: null` + a local model name are latent failures — they will 400 on the next run. Fix them proactively, not just the ones already erroring.

## Fix — VERIFIED tool mechanics (read carefully)
The `cronjob` **update** tool does NOT persist `base_url` when it is nested inside the `model` object. It MUST be passed as a separate TOP-LEVEL parameter. Passing it nested silently drops it, leaving `provider: custom` pointing at OpenRouter → the cron keeps 400-ing and you think you fixed it.

CORRECT — `base_url` at top level, alongside `model`:
```
cronjob action=update
  job_id:   <id>
  model:    {"model": "<your-model> "provider": "custom"}
  base_url: "http://<lab-host>:11434/v1"
```

WRONG — `base_url` nested in `model` is silently dropped:
```
cronjob action=update
  job_id: <id>
  model: {"model": "<your-model> "provider": "custom",
          "base_url": "http://<lab-host>:11434/v1"}   # <-- dropped, fix fails
```

For local M2 Ollama the working values are `provider: "custom"` + `base_url: "http://<lab-host>:11434/v1"`. A known-good reference job is **"<content-pipeline> Analytics Daily Report"** (`<job-id>`): `provider: custom` + `base_url: http://<lab-host>:11434/v1` with `model: <your-model> reporting `ok`. Replicate its exact shape.

### GOTCHA — the cronjob tool + CLI CANNOT set base_url; patch jobs.json (verified 2026-08-13)
Even with `base_url` passed as a top-level param, the `cronjob` tool `action=update` returns **`No updates provided.`** and drops it (it silently rejects `base_url` as not-an-update-field), and `hermes cron edit`'s CLI exposes `--model` and `--provider` but has **NO `--base-url` flag** in its help. So the tool-based path above (from the earlier 400-class note) does NOT work for setting `base_url` — don't keep retrying it (`repeated_exact_failure` loop). The reliable fallback:
1. Set `model` + `provider` via `hermes cron edit <id> --model <m> --provider custom` (this DOES persist).
2. `base_url` is STILL `None` afterwards — and with `provider: custom` + no base_url the job falls through to the config default (`openrouter.ai/api/v1`), which rejects local model names. You MUST set it.
3. Patch the source of truth directly — backup then JSON-edit `/<home>/.hermes/cron/jobs.json` for that one job:
   ```python
   import json, shutil, datetime
   p='/<home>/.hermes/cron/jobs.json'
   shutil.copy(p, p+'.bak_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
   d=json.load(open(p))
   for j in d['jobs']:
       if j.get('id')=='<JOB_ID>':
           j['base_url']='http://<lab-host>:11434/v1'; j['model']='<your-model> j['provider']='custom'
   json.dump(d, open(p,'w'), indent=2, ensure_ascii=False)
   ```
   The scheduler reloads `jobs.json` each tick; `cronjob action=list` reflects the change immediately. Keep the change small (one job's routing) and always back up first. Verified on <content-pipeline> Pipeline Watchdog (`<job-id>`) + Weekly App-Trends Brief (`<job-id>`).

## Identify broken crons
`cronjob action=list` → scan every entry for `model` = a local Ollama name AND `provider` = `null`. Apply the fix to ALL of them in one batched round of parallel `update` calls (they are independent). See `references/cron-model-fix-example.md` for a real bulk-repair transcript.

## Silent-skip: gateway not running (no error, no status change)
A cron can miss its slot WITHOUT ever showing `error`. Symptoms: `last_status` is still `ok` (from a prior good run), `last_run_at` is stale, and `next_run_at` has advanced past the missed time. This means the scheduler simply was not alive at fire time — cron only fires while the gateway process is up. The scheduler does NOT catch up missed ticks; it just moves `next_run_at` forward.

### Diagnostic procedure (root-cause, not guesswork)
1. `cronjob action=list` → find the job. Confirm `last_status` is `ok` and `next_run_at` skipped the expected time. `enabled: true`, `state: scheduled`, not paused.
2. Check the gateway process is alive NOW: `ps aux | grep "hermes.*gateway run" | grep -v grep`. Note its start time with `ps -o lstart= -p <PID>`.
3. `uptime` / boot time: if the machine has been up only minutes and the gateway started *after* the missed cron slot, the gateway was down during the fire window — confirmed root cause.
4. `date -u` + `TZ=Pacific/Auckland date` to confirm the slot math (cron times are UTC; NZT = UTC+12/13).
5. Other crons in the same window will also be missing — check siblings to confirm it's a gateway-availability gap, not a single-job config break.

### Action when confirmed
- Manually re-fire the missed job: `cronjob action=run job_id=<id>`. It runs under the now-live gateway; result lands in the configured delivery target.
- CAUTION: `cronjob action=run` re-arms `next_run_at` but may NOT immediately refresh `last_run_at`/`last_status` — the run is async. Don't treat the unchanged fields as a failure.

### The real fix — keep the gateway alive (boot-order gap)
A manually-launched `hermes gateway run` dies when the host sleeps/reboots, silently skipping every cron in that window. Options, in order of robustness:
- **Best (24/7 fire immunity): run the gateway on the always-on M2 (<lab-host>)** instead of the WSL desktop. It survives the user's Windows sleep/reboot cycle entirely. The M2 already hosts Ollama, so cron firing there is immune to desktop downtime.
- **Auto-start on WSL login (faster/responsive, still dies on full reboot)**: systemd-user service. VERIFIED procedure below — this is the recommended local path when the user prioritizes latency over 24/7 immunity.
- **External watchdog** (OS task scheduler, NOT Hermes cron): pings the gateway and restarts it if dead. But a dead gateway also kills the watchdog's own scheduler — so the watcher must live outside Hermes.

#### VERIFIED: systemd-user auto-start (local box, WSL2 Ubuntu)
This is the concrete procedure — do NOT hand-roll a bare unit; let Hermes own it.

1. Confirm systemd --user is available: `systemctl --user status` (WSL2 Ubuntu ships it running).
2. Write a minimal unit to `~/.config/systemd/user/hermes-gateway.service` (create the dir). Hermes will REWRITE it on first launch under systemd — see gotcha below — so a bare stub is fine:
   ```
   [Unit]
   Description=Hermes Agent Gateway
   After=network-online.target
   Wants=network-online.target
   [Service]
   Type=simple
   ExecStart=/<home>/.local/share/pipx/venvs/hermes-agent/bin/python -m hermes_cli.main gateway run --replace
   Restart=always
   RestartSec=3
   [Install]
   WantedBy=default.target
   ```
   (Path: the venv python is `/<home>/.local/share/pipx/venvs/hermes-agent/bin/python`. Get it live with `which hermes` → resolve the symlink, or just use `hermes gateway run --replace` if on PATH.)
3. `systemctl --user daemon-reload`
4. Stop any manually-running gateway first so systemd owns the socket cleanly: `kill <manual_PID>` (the `--replace` flag also handles takeover, but killing avoids a brief double-bind).
5. `systemctl --user enable --now hermes-gateway.service` → starts now AND on every WSL login. `enabled` symlink appears under `default.target.wants/`.

**GOTCHA — Hermes self-rewrites the unit (CRITICAL):**
On first launch under systemd, Hermes detects `under_systemd=yes` and overwrites `hermes-gateway.service` with its own hardened version. That rewritten unit ADDS two env vars your jobs depend on:
- `HERMES_HOME=/<home>/.hermes`
- `Environment=PATH=...` that INCLUDES the Windows paths (`/mnt/c/WINDOWS/system32`, `.../WindowsPowerShell/v1.0/`, etc.)

Without those, cron jobs that shell out to `powershell.exe` / `cmd.exe` (<content-pipeline> pipeline, YouTube cross-post) will FAIL even though the gateway is "up". So: NEVER ship a hand-written unit that omits these — either let Hermes rewrite it (recommended) or copy its rewritten form verbatim. After enabling, re-read the file to confirm Hermes rewrote it and the PATH/HERMES_HOME lines are present.

NOTE — this Windows-PATH gap is NOT unique to the gateway. ANY systemd --user unit launched
from WSL that shells out to `cmd.exe`/`powershell.exe` (e.g. the TTS playback watcher in the
`voice-response` skill) hits the exact same silent failure unless its unit sets
`Environment=PATH=.../mnt/c/WINDOWS/system32...`. If a WSL systemd service "runs" but its
Windows-side call does nothing, suspect the missing Windows PATH first.

**GOTCHA — socket race on kill-test:**
If you kill the gateway PID to verify `Restart=always`, the new instance may exit 1 once because the old socket is still in TIME_WAIT. systemd retries (RestartSec=5) and comes up clean on the next attempt. Don't read a single exit-1 as a broken service — wait ~6s and re-check `systemctl --user status` for `active (running)`.

**Verification of self-healing:**
```
kill $(pgrep -f "hermes_cli.main gateway")   # systemd respawns it
sleep 6
systemctl --user status hermes-gateway.service --no-pager | grep -E "Active:|Main PID"
ps aux | grep "hermes_cli.main gateway" | grep -v grep   # should show a fresh PID + child
```

See `references/silent-skip-diagnostic.md` for the full worked example (<content-pipeline> morning job missed 2026-07-16 because gateway started 3h after the 08:00 NZT slot).
See `references/gateway-systemd-autostart.md` for the complete unit file (pre- and post-Hermes-rewrite) and command transcript.
See `references/cron-model-fix-example.md` for a real bulk-repair transcript (the provider:null → 400 class).
See `references/windows-conhost-trace.md` for the parent-PID hunt that finds which Windows process owns a rogue console window (the "terminals pop up after pausing crons" case).

## PITFALL — pausing crons does NOT stop Windows-side orchestrators
`cronjob action=pause` (all jobs) silences the Hermes scheduler. It does NOT kill processes that were launched OUTSIDE Hermes — e.g. a Windows Scheduled Task (`schtasks`) or a manual launch that started `python C:\pipeline\orchestrator.py` or a custom listener (`jarvis_ear.py`). Those run their OWN schedulers (APScheduler) and keep spawning visible console windows (`conhost.exe`) on the desktop. Symptom the user reports: "I paused all crons but random CLI terminals still pop out of nowhere."

REAL root cause in this lab (2026-07-18): the <content-pipeline> orchestrator (`C:\pipeline\orchestrator.py`) and a custom listener (`C:\Users\<win-user>\jarvis_ear.py`) were started via Windows startup/manual launch, NOT by Hermes cron. Pausing 14 Hermes crons did nothing to them. The fix was to kill those specific Windows PIDs directly via `powershell.exe Stop-Process`.

### Procedure when "terminals still pop up after pausing crons"
1. List live Windows processes + their command lines from WSL:
   `powershell.exe -NoProfile -Command "Get-Process | Where-Object { $_.Name -match 'python|cmd|powershell|conhost|pythonw' } | Select-Object Name, Id, Path, StartTime | Format-Table -AutoSize | Out-String -Width 200"`
2. Map each visible console host to its owner. The key insight: every visible window has a `conhost.exe`; its `ParentProcessId` is the process that opened the window. Use the parent-PID hunt (see `references/windows-conhost-trace.md`) to find which `python.exe`/`cmd.exe` owns the rogue conhosts.
3. Ignore benign conhosts: parent = `postgres.exe`, `ollama.exe`, `wslhost.exe`, `WindowsTerminal.exe` (your own terminal), AMD `cmd.exe` service. Kill ONLY the ones whose parent is an orchestrator/listener (e.g. `orchestrator.py`, `jarvis_ear.py`).
4. Kill the owner PIDs: `powershell.exe -NoProfile -Command "Stop-Process -Id <PID> -Force"`. The conhosts die with their parent.
   - **ALSO match `pythonw.exe`**, not just `python.exe`. `jarvis_ear.py` ran as `pythonw.exe` (windowless) with a SELF-RESPAWN loop: `pythonw 10964` spawned child `pythonw 19412`. Killing only the visible `python.exe` instance left the `pythonw` orphan alive, and pop-ups CONTINUED. Kill every PID whose command line is the rogue script — both `python.exe` AND `pythonw.exe`, parent AND child.
   - Verify with a second `Get-Process -Name python,pythonw | Where-Object { $_.Path -match 'jarvis_ear|orchestrator' }` — if anything remains, kill it too.
5. To make it permanent (survive reboot): DISABLE (not unregister) the Windows startup task, so the task config is kept for a later relaunch:
   `powershell.exe -NoProfile -Command "Disable-ScheduledTask -TaskName '<content-pipeline>PipelineOrchestrator'"`
   Use `Get-ScheduledTask | Where-Object { $_.TaskName -match '<content-pipeline>|Pipeline|Orchestrat|Jarvis' }` to enumerate, then disable each by exact name. (Only `Unregister-ScheduledTask` if the user wants it GONE permanently — usually they want it paused, like the crons.)
   **CRITICAL GOTCHA:** disabling the task does NOT kill the already-running process. If a `pythonw.exe`/`python.exe` instance of the script is still alive, it keeps spawning windows and self-respawns. You MUST kill the live PIDs (step 4) AFTER disabling the task, and re-verify none remain.

CAUTION: A Hermes cron that shells out to `powershell.exe -Command "python C:\pipeline\..."` is a SECONDARY source of pop-ups and IS stopped by pausing — but the persistent orchestrator/listener is the primary one and must be killed separately (and its live orphan too).

## PITFALL — config-backup cron "errors" because the tarball exceeds GitHub's 100MB limit
A no_agent backup cron that tars `~/.hermes` can report `last_status: error` even when the
script "runs" — because it swept **per-profile runtime dirs** (`profiles/*/node`,
`profiles/*/sessions`, `profiles/*/state.db`, `profiles/*/logs`, `profiles/*/bin`, `__pycache__`)
into the tarball. Verified 2026-08-04: 945MB for what should be a few MB → aborts every run.

Symptoms: `last_status: error`, script prints `ERROR: tarball exceeds GitHub 100MB limit`.
Different from the 400-model / silent-skip classes.

**Fix (staging pattern):** don't tar `~/.hermes/profiles` in place and exclude — **stage only
the essentials into a temp dir, then tar that once** (also avoids multi-member-gzip junk from
appending profile tarballs, which some tools misread). Stage: `config.yaml*`, `.env`,
`auth.json`, and `skills/ memories/ cron/ scripts/ kanban.db` snapshots + per-profile ONLY
`config.yaml`, `SOUL.md`, `memories/`. Result drops 945MB→13MB and pushes cleanly. Keep the
existing prune (keep last 7, and also drop any stray >100MB stragglers).

Check the bloat with `du -sh ~/.hermes/profiles/*/` — a profile holding a 1GB `node/` +
`state.db` is the tell.

## PITFALL — config drift guard: cron silently skips ("Skipped to prevent unintended spend")
A cron with `model: null` / `provider: null` (unpinned) can be stopped from firing by the
"unintended spend" guard **when the global default inference config drifts** — i.e. the
model the job would inherit under the default provider changed since the job was created.
Observed live 2026-08-13 on **<content-pipeline> Pipeline Watchdog** (`<job-id>`) at 20:00:

```
RuntimeError: Skipped to prevent unintended spend: global inference config drifted since
this job was created (model 'deepseek/deepseek-v4-flash-0731' -> 'anthropic/claude-opus-5-fast'),
and this job is unpinned. No inference call was made.
To run on the new config, pin it explicitly:
  cronjob action=update job_id=<id> provider=<provider> model=<model>
(or pin the original values to keep them). See #44585.
```

**Symptoms:** `last_status: error` in `cronjob action=list`, but NOT a 400 model-ID error,
NOT a silent-skip (it DID attempt and error), and NOT a VRAM OOM. The executions record
(`~/.hermes/cron/executions.db`) shows `status=failed` + this error string.

**Root cause:** an **unpinned** job (no explicit `provider`/`model`) inherits the current
global default. When the admin/user changes the active model (e.g. switching the session to
`anthropic/claude-opus-5-fast`), every unpinned job sees its implicit model change and the
guard refuses to fire to avoid surprise spend — even if the job is a tiny/`no_agent`-ish one.

**Diagnose the affected set in one pass:** read `~/.hermes/cron/jobs.json` (the source of
truth) and list every job with `model: None` + `provider: None` (they inherited the default
and are at drift risk), versus the few that pin a local model (`<your-model> +
`provider: custom` + `base_url` M2 — safe). Only the unpinned set can trip this guard.

**Fix — two options:**
1. **Pin the job explicitly** (recommended when you know what it should use) —
   `cronjob action=update job_id=<id> provider=<provider> model=<model>` (provider/model
   top-level; `base_url` top-level too per the 400-class fix). For a local job:
   `model=<your-model> provider=custom base_url=http://<lab-host>:11434/v1`.
   For a cloud job, pin the model the job actually needs.
2. **Pin the original values to keep prior behaviour** if you must not move the job's model.

**Do NOT leave an unpinned job "fine" because it reported ok before** — the drift guard
fires only AFTER config drift; a job that looks healthy today can skip tomorrow if the
default model changes again. If you can convert it to `no_agent` (deterministic script job,
no LLM needed), that is the most robust — it has no inference dependency at all. But note
`no_agent` + `model: null` is fine precisely because no model is invoked.

**Surface, don't hide:** two or more unrelated crons erroring with this SAME message at once
points at a single global config change, not N separate breakages — fix by pinning each or
converting to no_agent, and mention the model switch to the user so they're aware the
default changed.

**AUDIT THE WHOLE SET AT ONCE, don't fix one-by-one when asked (2026-08-14, <operator> correction).**
When a user asks you to fix a drift-skipped cron, do NOT pin just that one — run a single
pass over `/<home>/.hermes/cron/jobs.json` and list EVERY job with `model: None` +
`provider: None` + `not no_agent` (the full drift-risk set), then decide which to pin to M2
and which to convert to no_agent, and pin them all in one go. Leaving the rest of the
unpinned set "healthy because they reported ok before" guarantees the NEXT config drift
silently kills them the same way. As of 2026-08-14 the still-unpinned drift-risk set was:
<store-pod-cron> (<job-id>), hindsight-weekly-reflect, <devops-digest> (<job-id>),
<shop-seo-cron> (<job-id>), daily-link-check (<job-id>), <engine-daily-cron>
(<job-id>) — plus the <content-pipeline> guard crons are covered in `<content-pipeline>-pipeline-scheduling`.

## PITFALL — agent cron fails with HTTP 500 / `cudaMalloc failed: out of memory` (VRAM OOM on the inference host)
A Hermes cron pointed at a LOCAL Ollama-hosted model (e.g. `<your-model> on M2)
reports `last_status: error` with a distinctive body that is NOT a 400 model-ID error:

```
RuntimeError: HTTP 500: llama-server process has terminated: exit status 1:
cudaMalloc failed: out of memory
alloc_tensor_range: failed to allocate CUDA0 buffer of size <N>
error loading model: unable to allocate CUDA0 buffer
```

**Root cause:** every run must LOAD the model into the inference host's VRAM to run the
agent loop. When that host's GPUs are already near-saturated (this lab: M2 at ~90–94%
per GPU, only a few hundred MiB free), Ollama cannot allocate a CUDA buffer for the model,
so the whole job aborts. This is distinct from both the provider/base_url 400 class and the
silent-skip class — the script the cron runs is fine; the LLM loading is the blocker.

**Why it's a self-feeding trap:** it's exactly when M2 is heavily loaded that you most want
the health/monitor cron to work, and it's exactly then that the job can't load its model.

**Fix:** this class of job almost never needs an LLM — it just runs a deterministic shell
script. Convert it to a `no_agent` script job per the section below (same mechanics:
`cronjob action=update job_id=<id> no_agent=true prompt="" script="<basename>.sh"`,
bare filename in `~/.hermes/scripts/`, `prompt` cleared). This removes the VRAM dependency
entirely, costs zero tokens, and makes the cron robust exactly when the host is under load.

**Verify:** `cronjob action=list` shows `no_agent: true` + `script:`; a manual
`cronjob action=run` produces a clean output file marked `Mode: no_agent (script)` with no
OOM error. Worked example (2026-08-07, lab-health-check cron `<job-id>`): agent job 400/500'd
for days because M2 VRAM was at 90–94%; converted to `no_agent` → instant clean health report.

**Related lab finding (don't ignore):** when a non-cron workload needs to load a large model
onto a saturated host, free a slot first (`ollama-model-vram-setup` / `check-m2-vram` skills).
Converting the cron fixes the cron, but the underlying host-VRAM pressure is a separate real
signal worth surfacing to the user.

See `references/vram-oom-cron-fix.md` for the full error transcript and fix transcript.

## Converting a cron to a `no_agent` SCRIPT job
When a job is deterministic (e.g. a backup+push script), switch it from an
LLM-prompt job to a `no_agent` script job so it runs the script's stdout
verbatim with zero token cost. VERIFIED mechanics (2026-07-19):
- `cronjob action=update job_id=<id> no_agent=true prompt="" script="filename.sh"`
- **`script` MUST be a bare filename** in `~/.hermes/scripts/` — passing
  an absolute (`/<home>/.hermes/scripts/x.sh`) or `~/...` path is
  REJECTED: "Script path must be relative to ~/.hermes/scripts/". Write the
  file there FIRST, then pass only the basename.
- **`prompt` MUST be cleared to empty string** when switching to `no_agent`;
  an agent-prompt left in place is ignored but leaving it is sloppy. A
  `no_agent` job with `model: null` + `script` set runs the script and
  delivers its stdout to the configured target.
- **The script is invoked with NO command-line args** (the `prompt` is NOT
  passed as argv). A script whose no-arg branch prints usage/help will deliver
  that help text instead of real output — default to the report/main action when
  `sys.argv` is empty. Scripts used as `no_agent` cron targets must do something
  useful with no args.
- Keep `schedule` unchanged (e.g. `0 17 * * *`). The scheduler fires it
  the same way; only the execution path changes (script vs LLM loop).
- Verify: `cronjob action=list` → the job shows `script: filename.sh`,
  `no_agent: true`, `model: null`. Then `cronjob action=run job_id=<id>`
  to fire it once and watch the delivery target for the script's stdout.

## PITFALL — `no_agent` script job errors with `Script not found` (exit 127): script absent from `~/.hermes/scripts/` OR never exits (`--loop`)
Two distinct ways a `no_agent` script cron runs red:

**Case A — script not where the scheduler looks.** The scheduler resolves the
`script` field RELATIVE to `~/.hermes/scripts/` (a bare basename is REQUIRED and
an absolute path is rejected — see the convert section). If the real launcher
only lives in a repo dir (e.g. `project4-trading/execution/project4_live_watcher.sh`),
the cron dies with `last_status: error` and the run log says literally:
`Script not found: /<home>/.hermes/scripts/<name>.sh`. It fails EVERY tick
(dozens of identical errors) until the file exists there. Fix = write/copy a
launcher into `~/.hermes/scripts/<name>.sh` (bare basename), then
`cronjob action=run` to confirm.

**Case B — the script never returns (infinite `--loop`).** A launcher that runs
the target with `--loop --interval 900` (built for a manually-run persistent
daemon) NEVER exits. Fired by a 15-min cron, it hangs the run and/or spins up a
new never-dying process every interval. For a cron, the script MUST be
single-shot: do the work once (`--refresh` / main action) and exit. Reserve
`--loop` for a `systemd`/`nohup` daemon, never a cron-fired script.

**Where to look — the scheduler's own run log (ground truth):** every run is
written to `~/.hermes/cron/output/<job_id>/<timestamp>.md`
(e.g. `/<home>/.hermes/cron/output/<job-id>/2026-08-20_06-13-52.md`).
This file holds `Script not found: ...` or the actual traceback — read it FIRST
when a cron is red (don't trust the one-line `last_status`, which lags). It also
surfaces the full history of failures across all ticks.

**Verify the fix at the SCHEDULER (not just by hand-running the script):** after
placing the file, `cronjob action=run job_id=<id>`, then read the newest
`~/.hermes/cron/output/<job_id>/` file. A clean run shows `Mode: no_agent
(script)` + the script's stdout with NO `Script not found` line. Hand-running the
script proves the SCRIPT works; only the scheduler run proves the cron can FIND
it.

See `references/no_agent_script_not_found.md` for the full transcript (dozens of
`Script not found` failures → single-shot launcher placed in `~/.hermes/scripts/`
→ clean run).

## PITFALL — `no_agent` `.py` cron dies on IMPORT: runs under system python3, not the project venv (Case C)
Distinct from Case A (`Script not found`) and Case B (`--loop` hang). The script IS present in `~/.hermes/scripts/`, but the run log shows a Python `ModuleNotFoundError` (e.g. `No module named 'feedparser'` / `'pandas'` / `'yfinance'` / `'ccxt'`) or an import-time crash. Root cause: Hermes executes `no_agent` `.py` scripts with the **system python3**, which does NOT have your project's virtualenv dependencies. So any project script that `import`s pandas/yfinance/feedparser/ccxt (common in trading/monitor/notifier crons) fails on import even though it runs fine by hand in the venv.

**Verify:** the run log (`~/.hermes/cron/output/<job_id>/<ts>.md`) shows the traceback. Cross-check `python3 -c "import feedparser"` (system — fails) vs `<venv>/bin/python -c "import feedparser"` (project venv — ok).

**Fix — wrap the project `.py` in a `.sh` that execs the project venv python:**
1. Write `~/.hermes/scripts/<name>.sh`:
   ```bash
   #!/bin/bash
   # Run <name>.py with the project venv (has pandas/yfinance/feedparser/ccxt).
   cd /<home>/hermes-workspace/<project>/execution   # if the .py needs repo-relative imports
   exec /<home>/hermes-workspace/<project>/.venv/bin/python <name>.py
   ```
   If the `.py` does `sys.path.insert(0, parent_of_its_own_location)` to import sibling `core/`/`execution/` packages, the `cd` into the repo dir is REQUIRED so that path resolves — a bare copy of the `.py` into `~/.hermes/scripts/` will break those imports.
2. `chmod +x ~/.hermes/scripts/<name>.sh`.
3. Repoint the cron's `script` field from `<name>.py` to `<name>.sh`. The `cronjob action=update` tool REJECTS a single-field `script` change ("No updates provided.") — patch `/<home>/.hermes/cron/jobs.json` directly (backup first, match on `"id"`, set `"script": "<name>.sh"`). The scheduler reloads each tick.
4. Verify at the SCHEDULER: `cronjob action=run job_id=<id>`, then read the newest `~/.hermes/cron/output/<job_id>/` file — clean `Mode: no_agent (script)` + the script's stdout, NO `ModuleNotFoundError`.

**Prevention — watchdog + paused audit:** notification/monitor crons fail SILENTLY (error OR `paused: true`) and the user only notices the absence of alerts. (a) Audit for `paused: true` crons — a monitor paused after a banked trade stays silent until re-armed. (b) Add a cron that checks the others' `last_status`/paused state and pings Telegram on failure, turning silent breaks into loud ones. See `references/no_agent_venv_import_error.md` for the full trading-cron repair transcript (IFT/US pullback watchers + Project4 aggregator, 2026-08-21) and a reusable venv-wrapper template.

## PITFALL — `deliver` double-sends / spams when the script already pushes to Telegram itself
If the script's own code sends alerts to Telegram directly (e.g. via the Bot API
using the token + chat id from the Hermes env store — common in trading/monitor
notifiers), do NOT also set the cron `deliver` to a Telegram target. Otherwise you
get BOTH deliveries (cron stdout + the notifier's own message) = duplicates, AND
on idle ticks the script prints a status line (`0 new`, `tick: ... signals`) that
the cron then pushes every interval = per-tick spam. Fix = set `deliver: "local"`
on that cron; the notifier is the only Telegram path. (Inverse of
"silent-when-idle delivers nothing": a script that prints a status line every tick
is NOT silent, so a Telegram `deliver` turns it into spam.)

## PITFALL — `deliver` target + `repeat` on `create`
- **`deliver` defaults to `"local"` (save-only, NO push) for script/`no_agent` jobs when omitted.** `deliver:"local"` saves the run's stdout but does NOT deliver it to any chat. If the origin session is closed, you see nothing. To PUSH a digest to a live chat, set `deliver:"origin"` EXPLICITLY when creating the job — omitting `deliver` does NOT default to origin for script jobs (it defaults to local).
- **`deliver:"origin"` is captured at CREATION TIME** — it delivers to the session that created the job. If that session is later closed, delivery is lost even though the cron keeps running. Fix: re-create (or `cronjob update deliver:"origin"` from) the live session to re-point it. With the gateway down, `deliver:"all"` (fans out to connected home channels like Telegram) also reaches nothing, so origin (the current session) is the only live target.
- **`repeat` on `create` must be OMITTED for recurring jobs.** Passing `repeat:"forever"` (a string) fails with `"'<=' not supported between instances of 'str' and 'int'"`. Recurring schedules (`every 5m` / cron expr) default to `repeat:"forever"` when `repeat` is omitted. Only pass `repeat` as an INTEGER for one-shot/limited jobs — never the string `"forever"`.
- **Silent-when-idle script jobs deliver nothing on idle ticks** — that's correct, not a bug. With `no_agent:true` + `script:"file.sh"`, the script's stdout is delivered verbatim to the `deliver` target; if the script prints nothing (by design, e.g. when no new input), nothing is delivered.
- **`deliver` target MUST be the canonical name from `send_message action='list'` — NOT a raw chat ID.** Passing `telegram:8129060667` (the numeric chat id) is *accepted* by `cronjob create` but is NOT validated against real recipients — it can silently never deliver. Always run `send_message action='list'` FIRST and copy the exact target string it prints (e.g. `telegram:<operator> (dm)`, `discord:#general-chat`). Keep `deliver` set to that verbatim string.
- **VERIFY a delivery target before trusting the cron.** After creating the job, send a one-line test via `send_message target=<exact_target>`; success returns `message_id` + `mirrored: true`. If it fails, the cron will too — re-list, re-copy the target, then re-test. See `scripts/event_watchdog.py` for the full event-based watchdog pattern this enables (silent ticks, alert-only-on-event delivery).

## PITFALL — a HOST IP change silently breaks every cron (and profile) pointing at the OLD IP
When a lab machine's LAN IP changes (e.g. M3 moved <lab-host> → <lab-host> on 2026-08-04),
every cron whose `base_url` / provider still pins the old IP keeps RUNNING with `last_status:
ok` — because the shipper can't reach that host to reject. The failure is silent until you look:
no error, no 400, just nothing delivered (or a fallthrough to a different host). In this lab M3
profiles (ip-guard, qa-reviewer → <your-model> had providers listing ONLY the dead `.9`, so they
were effectively unreachable for their assigned model until re-pointed.
**After any host IP change, re-audit ALL of:**
1. Every profile's `providers:` block in `~/.hermes/profiles/*/config.yaml` (main host +
   base_urls; the true host must be listed, ideally FIRST).
2. Every hermec cron's `base_url` (top-level) whose model lives on that host.
3. Any pipeline/server config that shells out to that host by IP.
Check the live IP: `curl <host>:11434/api/tags`. Fix = update the IP, put the true host first so
wasted dead-IP round-trips don't slow first calls. Back up configs first (profile edits are
user-owned — get explicit go, then `cp` to a `_bak_<ts>` dir).
When asked to audit scheduling or produce a "what runs when / which machine is free"
timetable, do NOT trust only the Hermes cron list — the <content-pipeline> pipeline self-schedules
via Windows schtasks + its own APScheduler, so the real picture spans THREE layers.
Cross-check every LLM-using cron (Hermes + Windows + orchestrator + channel post_times)
against M2 render windows to find clashes; move offending crons to a free window; and
separate user/creative output blocks from the sub-agent autonomous window. See
`references/schedule-timetable-audit.md` for the full audit method + the verified
2026-08-04 layout (renders 07/11:30/18, M2 blocked 06:50–09:10 / 11:20–13:40 /
17:50–20:10, sub-agent window 20:11–06:49, creative blocks 09:30–11:19 & 14:30–17:49 M–F).

## PITFALL — self-heal / watchdog that only checks `last_status` flags is DECORATIVE (2026-08-22)
A monitoring cron (e.g. `cron_self_heal.py`, the Lab Integrity Monitor) that only reads each
job's `last_status` / `last_fire_error` field and reports "ok" when those are clean **will miss
real breakage**. It checks the flag, not reality. Observed failure (2026-08-22):
- The <content-pipeline> Pipeline Watchdog cron (`<job-id>`) was in `last_status: error` since
  2026-08-20. The self-heal cron saw it but **never restarted it** → 39 days of silent
  non-posting. The self-heal reported green because it only inspected flags, never acted.
- A **wedged kanban worker process** (Hermes sub-agent, PID alive, 40% CPU, orphaned task)
  held M2's model slot and blocked <content-pipeline> — but no cron inspected *live process state*, so
  nothing killed it. The "ok" status was a lie.

**The lesson: a watchdog is only as good as what it verifies. Verify REALITY, not flags:**
1. **Live process state** — is the process actually alive and not wedged (check `ps`, not just
   a stored `state` field)? A stuck-but-"scheduled" worker is a real outage.
2. **Actual delivered output** — did the job produce its artifact / post / file this period?
   `last_status: ok` means the command exited 0, NOT that it did the thing. Check the output
   file / posted count / sidecar, not the flag.
3. **Act, don't just report** — if a watchdog/monitor cron is `error` or `paused`, the healer
   must *restart or re-arm it* (and alert loudly), not log "ok" and move on. A healer that only
   prints green is worse than no healer — it hides the break.
4. **Kill wedged workers** — if a sub-agent process is alive but its task is orphaned / its
   board is empty, it's holding compute for nothing. The healer should `kill -9` it and free
   the slot, then let the next scheduled run retry cleanly.

This is the same family as "last_status: ok can hide wrong output" (above) but one level up:
the *monitor itself* must be monitored against reality, or the whole self-healing claim is
hollow. The user's standing demand: "if it's broken, tell me within the tick, don't report ok
while nothing fired for 39 days."

## PITFALL — a cron's `last_status: ok` can hide WRONG OUTPUT (stale-source bridge)  2026-08-04
A cron that launches a downstream script can report `ok` while the script does the *wrong*
thing — not a crash, just bad output. Observed: the 22:00 **YouTube cross-post** cron ran
green (`last_status: ok`) but uploaded **3 OLD videos** to the channel instead of that day's
2 new ones. User: "it's posting old content and not the latest two videos."
- **The cron's `ok` only means the invoked command exited 0.** It says nothing about whether
  the script picked the right INPUT. This is the same family as Rule 31 (status-ok ≠ real
  deliverable) — here the "deliverable" was the wrong set of files.
- **Diagnose "wrong content posted" by checking the bridge's SOURCE + FILTER, not the cron
  status.** The YT bridge (`yt_queue.py`, the script the cron actually runs) pulled
  newest-unposted from `ssh m2 "/pipeline/final/"` — a STALE dir that held nothing past the
  last real production render, while the day's actual FINAL videos live locally in
  `C:\\pipeline\\test_videos\\`. With NO date filter, it grabbed the 3 newest *unposted* stale
  files (Jul 9/10 content) and shipped them. Two compounding defects: wrong/stale source dir
  + no same-day filter.
- **Fix pattern for cross-post/publish bridges after a "wrong content" report:**
  1. List what the channel actually has now (`powershell python yt_list_channel.py`) — see
     exactly what wrongly went up, don't trust memory.
  2. Confirm where the day's REAL finals live (often the manual/post path keeps them in
     `test_videos\\`, NOT on the referenced M2 production dir) — the bridge must read THERE.
  3. Add a **same-day filter** (filename prefix `YYYYMMDD_` + channel + `_FINAL`, exclude
     `_TEST/_FIXED/_CAPFIX` staging variants) and pull titles/desc/tags from the day's real
     post-record JSON (e.g. `data/ch1/content_history.json`) matched by slot/format.
  4. Back up the old script first, then verify the fix stages/queues ONLY today's files.
- **Titles on already-uploaded filename-garbage videos** are recoverable from the day's post
  record even when the sidecar `.meta.json` is missing — match the uploaded filename's date+slot
  to `content_history.json` and rewrite via `videos().update` (needs `youtube.force-ssl` scope).
  This nuanced the earlier "old topics are NOT recoverable" claim (true for pre-sidecar
  orphans with no history record, false when content_history still has the day's topics).

## What NOT to touch
- `no_agent` script jobs (`model: null`, `script: "..."`) — no model is invoked.
- Jobs already on a correct provider: `custom:openrouter-t31`, `custom` → OpenRouter for cloud models (`deepseek/deepseek-v4-flash`, `anthropic/claude-sonnet-4`).
- Agent jobs with `model: null` — they inherit the default interactive agent model and work fine.

## Verification
- **Structural equivalence to the known-good cron is sufficient proof** the 400 is gone (same `provider` + `base_url`). You do not need a live run.
- CAVEAT: `cronjob action=run` may re-arm the schedule (`next_run_at` advances) WITHOUT refreshing `last_status`/`last_run_at`. Do NOT treat a manual run as a clean success/failure signal — watch the next real scheduled fire for `last_status: ok`.
- A direct live probe (e.g. `curl http://<lab-host>:11434/v1/chat/completions`) confirms endpoint reachability, but the user may block it; don't depend on it.
