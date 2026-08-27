# Silent-skip diagnostic — worked example

Context: <content-pipeline> Pipeline Morning (8am NZT) cron `<job-id>` was reported "missed".
Date of incident: 2026-07-16 (NZT). No error, `last_status` was `ok`.

## What the job list showed
- `last_run_at`: 2026-07-16T00:37:34 (a prior overnight run)
- `next_run_at`: 2026-07-16T20:00:00 (UTC) — i.e. the NEXT day's slot; today's 08:00 NZT tick was gone
- `last_status`: `ok`, no `last_delivery_error`, `enabled: true`, `state: scheduled`
- Schedule: `0 20 * * *` = 20:00 UTC = 08:00 NZT (CORRECT — not a config bug)

So: the job did NOT error, it simply never fired today.

## Root-cause proof
```
$ ps aux | grep "hermes.*gateway run" | grep -v grep
<user> 118 ... /<home>/.local/share/pipx/venvs/hermes-agent/bin/python -m hermes_cli.main gateway run --replace
$ ps -o lstart= -p 118
Thu Jul 16 10:54:33 2026
$ uptime
 10:55:21 up 0 min,  1 user, ...
```
The gateway started at 10:54 NZT — ~3 hours AFTER the 08:00 NZT fire window.
Machine uptime was 0 minutes at 10:55. The gateway (and therefore the scheduler)
was not alive at 08:00 NZT. Cron only fires while the gateway runs; the missed
tick was silently dropped and `next_run_at` advanced to the next day.

Sibling <content-pipeline> crons (midday/evening) showed `last_run_at` ~00:3x-00:4x today —
they fired overnight while the gateway WAS up, then it died before 08:00. This
confirmed a gateway-availability gap, not a single-job config break.

## Remediation applied
1. `cronjob action=run job_id=<job-id>` — re-fired under the now-live gateway.
2. Offered three fixes (in order of robustness):
   - Run gateway on always-on M2 (<lab-host>) — survives desktop sleep/reboot.
   - Auto-start on WSL login via systemd-user service / shell init.
   - External OS-level watchdog (NOT Hermes cron) that restarts a dead gateway.

## Key takeaways for future sessions
- A "missed cron with no error" is almost always the gateway being down during
  the fire window, not a broken job.
- Always check gateway PID start time + machine uptime BEFORE touching job config.
- `cronjob action=run` re-arms `next_run_at` but may not refresh `last_run_at`/
  `last_status` immediately (async) — don't read that as failure.
- Fix the boot-order gap (keep gateway alive), not the job.
