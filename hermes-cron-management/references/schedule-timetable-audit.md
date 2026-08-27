# Schedule / Timetable Audit — find every LLM-using cron and every M2 clash (2026-08-04)

Use when asked to audit scheduling, plan sub-agent times, or build a "what's running
when / which machine is free" timetable. Do NOT trust one source — Hermes crons are only
part of the picture; the <content-pipeline> pipeline self-schedules OUTSIDE Hermes.

## 1. Enumerate EVERY scheduling source (three layers, all touch M2)
1. **Hermes crons** — `cronjob list`. Gives time, model, provider, base_url,
   enabled/paused, `no_agent` (script vs LLM). Also shows the OLD superseded crons
   (e.g. <content-pipeline> Morning/Midday/Evening) — these are PAUSED but still present.
2. **Windows scheduled tasks** — the <content-pipeline> pipeline lives on the Windows side, NOT as a
   Hermes cron. Enumerate:
   `powershell.exe -NoProfile -Command "schtasks /query /fo CSV | ConvertFrom-Csv |
   Where-Object {$_.TaskName -match '<content-pipeline>|Pipeline|Watchdog|Orchestrator'} |
   Select TaskName,Status,NextRunTime"`
   Only Trust tasks that are Ready/Enabled. This session: `<content-pipeline>PipelineOrchestrator`
   Ready (live) + `<content-pipeline>DaemonWatchdog` Ready; old `<content-pipeline>DayPost/NightRender/Pipeline`
   Disabled (superseded).
3. **The orchestrator's own APScheduler** — `/mnt/c/pipeline/orchestrator.py` has the
   REAL slot schedule (read the `scheduler.add_job` blocks) + per-channel `post_times`
   in `channels/*.json`. Read it, don't assume. This session: morning 07:00, midday
   11:30, evening 18:00; trends_feed 14:00.

Also note per-channel `enabled: true/false` — ch2/ch3 were disabled, so only ch1's
slots actually fire.

## 2. Build the master day table (NZT) — tag each event by M2 resource
- M2 GPU (Wan render — inference OFF-LIMITS during it)
- M2 LLM inference (brief cron: <store-pod-cron> 03:00, trends 06:00, health check, YT
  cross-post 22:00)
- script/no-LLM (disk cleanup, security scan, config backup) — touches disk, not GPU

A python pass emitting every event with `[M2-LLM]`/`[GPU-BUSY]`/`[script]` makes the
clash check mechanical. Keep 10-min buffers around each render.

## 3. Clash check — flag LLM crons landing inside a render+buffer window
Recurring failure: an LLM cron scheduled at a time M2 is render-blocked. This session
found TWO at 09:00 (Lab Integrity Monitor + Hindsight weekly) inside the morning render
buffer (06:50–09:10). FIX: move the cron to a FREE window after the render resumes
(e.g. 09:15 daily) or to a non-render day (Hindsight → Sun 09:30);
`cronjob action=update job_id=<id> schedule="15 9 * * *"`.

## 4. Reserve user / creative output blocks (distinct from sub-agent windows)
The user reserves M–F blocks for {user}-{dev} collaboration (websites/app-dev/content/
Sovereign-AI/AI-agents/marketing). Those are OFF-LIMITS to scheduled sub-agents. This
layout: creative blocks 09:30–11:19 & 14:30–17:49 M–F; the clean overnight window
**20:11–06:49** is the dedicated autonomous sub-agent window. Bake this distinction in.

## 5. Deliver a readable timetable
- Markdown master: `<income-work-dir>/MASTER_SCHEDULE_TIMETABLE.md` (per-machine availability,
  clash log, sub-agent patterns, creative allocation).
- HTML view: `<income-work-dir>/Work_Timetable.html` (for the user to eyeball).
- Keep `<income-work-dir>/LLM_USAGE_TIMETABLE.md` as the machine×model×free-slot matrix.

## Canonical verified 2026-08-04 layout
- Renders 07:00/11:30/18:00; M2 BLOCKED 06:50–09:10, 11:20–13:40, 17:50–20:10.
- M2 free: 00:00–06:49, 09:10–11:19, 13:40–17:49, 20:10–23:59.
- M1 (<your-model> + M3 (4b/2b-aux) always free — use during M2 renders.
- Sub-agent autonomous window on M2 = 20:11–06:49 overnight.
- Creative blocks (ours, not sub-agents): 09:30–11:19 & 14:30–17:49 M–F.
- Lab Integrity 09:15 daily; Hindsight Sun 09:30; YT cross-post 22:00; <store-pod-cron> 03:00.
- Companion routing fix (same session): profiles M3 IP .9→.13 and M1→<wsl-gateway-ip> —
  see hermes-profile-config skill.
