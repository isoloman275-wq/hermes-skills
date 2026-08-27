# no_agent `.py` cron: ModuleNotFoundError (wrong Python / venv mismatch) — Case C

## Symptom
Run log `~/.hermes/cron/output/<job_id>/<ts>.md` shows:
```
Script exited with code 1
stderr:
Traceback (most recent call last):
  File "/<home>/.hermes/scripts/<name>.py", line N, in <module>
    import feedparser   # or pandas / yfinance / ccxt
ModuleNotFoundError: No module named 'feedparser'
```
The script IS present (Case A `Script not found` does NOT apply). It dies on import
because Hermes runs `no_agent` `.py` with **system python3**, which lacks the
project venv dependencies.

## Confirm
```
python3 -c "import feedparser"                                  # system — fails
/<home>/hermes-workspace/<proj>/.venv/bin/python -c "import feedparser"   # venv — ok
```

## Fix — venv-wrapper `.sh`
`~/.hermes/scripts/<name>.sh`:
```bash
#!/bin/bash
# Run <name>.py with the project venv (has the deps system python3 lacks).
cd /<home>/hermes-workspace/<proj>/execution   # if .py uses repo-relative imports
exec /<home>/hermes-workspace/<proj>/.venv/bin/python <name>.py
```
- `chmod +x ~/.hermes/scripts/<name>.sh`
- Repoint cron `script` `<name>.py` → `<name>.sh` via **direct jobs.json edit**
  (the `cronjob` tool rejects a single-field `script` change: "No updates provided.").
  Match on `"id"`, set `"script": "<name>.sh"`, back up first. Scheduler reloads each tick.
- Verify at the SCHEDULER: `cronjob action=run job_id=<id>` → read newest
  `~/.hermes/cron/output/<job_id>/` file: clean `Mode: no_agent (script)` + stdout,
  no `ModuleNotFoundError`.

## Real repair (2026-08-21, Project4 trading crons)
Three crons were red:
- `<ticker-pullback-watcher-1>` (<job-id>) — `Script not found`
  (the `.py` only lived in `project4-trading/execution/`, not `~/.hermes/scripts/`).
- `<ticker-pullback-watcher-2>` (<job-id>) — same `Script not found`.
- `<trading-brief-aggregator>` (<job-id>) — `ModuleNotFoundError: feedparser`.

Fix: created `ift_pullback_watch.sh`, `us_pullback_watch.sh`, `project4_aggregator.sh`
wrappers that `exec`
`/<home>/hermes-workspace/project4-trading/.venv/bin/python`, repointed the 3
crons via jobs.json edit. Verified: IFT/US ran (US even fired a real NVDA pullback
alert to Telegram), aggregator wrote its briefing, Telegram token valid (bot <telegram-bot>).

## Prevention — health watchdog
Notification/monitor crons fail SILENTLY (error or paused) and the user notices only
the absence of alerts. Add a cron that checks the others' `last_status`/paused state
and pings Telegram on failure. See `scripts/event_watchdog.py` for the event-based
pattern (silent ticks, alert-only-on-event delivery).
