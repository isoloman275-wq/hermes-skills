# Fleet Self-Heal — working patterns (verified 2026-08-22)

Two concrete fixes for the recurring "fleet wedges → <content-pipeline> dies → self-heal
reports ok" failure. Both are deployed and tested as of 2026-08-22.

## 1. Fleet Worker Watchdog (reaps wedged workers)

Deployed: `/<home>/.hermes/scripts/fleet_worker_watchdog.py`
Cron: `<job-id>`, schedule `*/15 23,0,1,2,3,4,5,6 * * *`, no_agent, script=`fleet_worker_watchdog.py`

Logic:
- `ps -eo pid,etimes,args` → find lines containing `work kanban task`.
- If elapsed minutes >= 90 → `kill -9` (wedged; a card should take 5-15 min).
- If current NZT hour >= 6 and minute >= 50 → kill ALL fleet workers unconditionally (<content-pipeline> owns M2 from 06:50).
- Telegram alert on every reap (so the user sees it without prompting).
- State file: `~/.hermes/scripts/.fleet_watchdog_state.json`.

Key: targets ONLY `work kanban task` processes — never touches legitimate
processes (gateway, project4 daemon, nextclaw, etc).

## 2. Decomposer self-limit

Patched `/<home>/.hermes/scripts/nightly-decomposer-cli.sh` — added at top
after `set -uo pipefail`:

```bash
HOUR_NOW=$(date +%H)
if [ "$HOUR_NOW" -ge 5 ]; then
  echo "=== decomposer: past 05:00, NOT queueing (fleet self-limit). Exiting clean. ==="
  exit 0
fi
```

So no card is queued after 05:00 → even a worker that wedges at 04:55 gets
reaped by 06:25, well before <content-pipeline>'s 07:00 slot.

## 3. Self-heal STALE check (the blind-spot fix)

The old `cron_self_heal.py` only checked `last_status == "error"`. Add this
branch (after the STUCK check, before the paused check):

```python
elif enabled and last_run_at:
    try:
        lra = datetime.datetime.fromisoformat(last_run_at)
        if lra.tzinfo is None:
            lra = lra.replace(tzinfo=datetime.timezone.utc)
        age_hours = (datetime.datetime.now(datetime.timezone.utc) - lra).total_seconds() / 3600
        sched = j.get("schedule")
        interval_h = 24 * 7  # default weekly
        if isinstance(sched, dict):
            expr = sched.get("expr", "")
            import re as _re
            m = _re.search(r"\*/(\d+)([mh])", expr)
            if m:
                n = int(m.group(1)); unit = m.group(2)
                interval_h = n/60 if unit == "m" else n
            elif expr.split()[0] != "*":
                interval_h = 24  # daily-ish
            # cron with specific weekday field (5th field != *) → weekly
            elif len(expr.split()) >= 5 and expr.split()[4] != "*":
                interval_h = 24 * 7
        threshold = max(interval_h * 3, 24)  # miss 3 runs (weekly) or 24h grace
        if age_hours > threshold:
            alerts.append(f"STALE: {name} ({jid}) last ran {last_run_at[:16]} ({age_hours:.0f}h) — DEAD")
            run(["hermes", "cron", "resume", jid])
    except Exception:
        pass
```

NOTE on threshold: use `3x interval` not `2x` for weekly crons — a weekly cron
that last ran 6 days ago is NOT stale (it runs every 7). 2x would false-positive.
3x means it must miss ~3 Sunday runs to be flagged. For daily crons 3x=72h grace
which is fine.

Also extract `last_run_at = j.get("last_run_at")` in the loop var block (the
original code referenced it inline and my first patch forgot to define it →
NameError; fixed by adding the assignment).

## 4. <content-pipeline> watchdog → no_agent

The <content-pipeline> Pipeline Watchdog cron (`<job-id>`) was an AGENT cron that errored
silently (last_status=error, no fire/delivery error — the LLM step died). Fixed
by converting to no_agent + script=`pipeline_watchdog.py` + deliver=telegram.
Verified: running the script directly catches today's 404 failure and sends
"alert sent: True". A watchdog must be a direct script, never an agent step that
can fail before reaching the script.
