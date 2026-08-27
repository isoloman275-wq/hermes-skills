# no_agent script cron: `Script not found` (exit 127) → fix (worked example)

Real transcript from Project4 FVG watcher cron `<job-id>` (2026-08-20).

## Symptom
`cronjob action=list` → job `<job-id>` `last_status: error`, `last_run_at`
stale. User: "FVG broken again where's my ETH notifications".

## Diagnostic — read the scheduler run log (NOT just last_status)
```
ls /<home>/.hermes/cron/output/<job-id>/
```
Every historical file (Aug 19 20:32 … 21:17, then Aug 20 06:13) said:
```
# Cron Job: Project4 Live Signal Watcher (FVG + Pullback)
**Status:** script failed
Script not found: /<home>/.hermes/scripts/project4_live_watcher.sh
```
Root cause: the launcher only existed in `project4-trading/execution/`, but the
cron resolves `script` RELATIVE to `~/.hermes/scripts/`.

## Fix
1. Wrote a SINGLE-SHOT launcher at `~/.hermes/scripts/project4_live_watcher.sh`:
   ```bash
   #!/usr/bin/env bash
   set -u
   cd /<home>/hermes-workspace/project4-trading
   exec ./.venv/bin/python execution/live_watcher.py --refresh --top-n 1
   ```
   (NO `--loop` — that never exits and hangs a 15-min cron.)
2. Set `cronjob action=update job_id=<job-id> deliver="local"` — the
   notifier already pushes real signals to Telegram directly (reads token + chat
   from the Hermes env store), so the cron must NOT also deliver stdout
   (avoids double-send + per-tick `0 new` spam).

## Verify at the SCHEDULER (proves the cron can find the file)
`cronjob action=run job_id=<job-id>` → read newest output file:
`/<home>/.hermes/cron/output/<job-id>/2026-08-20_06-13-52.md`:
```
**Mode:** no_agent (script)
[2026-08-19T18:13:52...] tick: 412 total signals, 0 new at latest bar (deduped/HOLD)
```
No `Script not found` → fixed. `0 new` = correctly silent (no actionable signal
on the latest 4h bar); a real FVG/pullback signal would have been sent via the
notifier. Hand-running `./.venv/bin/python execution/live_watcher.py --refresh
--top-n 1` proves the SCRIPT works; only the scheduler run proves the cron FINDs it.
