# Cron Model Fix — Bulk Repair Example

Real repair performed 2026-07-15. Pattern is reusable; specific IDs are illustrative.

## Symptom
`cronjob action=list` showed 9 jobs with `last_status: "error"` (or latent `ok` that would fail next run), all sharing:
- `model`: a local Ollama name (`<your-model> or `<your-model>
- `provider`: `null`
- `base_url`: `null`

Error text: `400 - ... is not a valid model ID` (name sent to OpenRouter).

## Jobs repaired (class of names — these break; the IDs change)
- Lab Health Check Daily
- <content-pipeline> Pipeline — Morning / Midday / Evening
- Web Design — <your-model> Build Queue
- YouTube Shorts — Cross-Post
- App Trends Scraper — Daily
- <store> POD — Design Generation Batch
- Mobile App Dev (uses `<your-model> not `<your-model>

## Correct call shape (verified)
```
cronjob action=update
  job_id:   <each id>
  model:    {"model": "<local name>", "provider": "custom"}
  base_url: "http://<lab-host>:11434/v1"
```
Batch all 9 as parallel calls in one turn (independent, no shared state).

## Gotcha proven the hard way
First attempt nested `base_url` inside `model`:
`model: {"model": "...", "provider": "custom", "base_url": "http://...:11434/v1"}`
→ returned job with `base_url: null`. The tool stripped it. Re-ran with `base_url` as a TOP-LEVEL param → persisted correctly.

## Verification outcome
- After fix, all 9 returned `provider: custom`, `base_url: http://<lab-host>:11434/v1`.
- Manual `cronjob action=run` on Lab Health re-armed `next_run_at` but did NOT refresh `last_status` — inconclusive from UI. Relied on structural equivalence to the known-good "<content-pipeline> Analytics Daily Report" cron (`<job-id>`, `ok`). Next scheduled runs (06:00, 07:00) confirmed.
- A direct `curl` endpoint probe was USER-BLOCKED — do not assume you can run it; structural proof is enough.
