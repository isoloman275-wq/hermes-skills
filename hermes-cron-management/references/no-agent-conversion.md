# LLM Cron Job → no_agent Conversion Pattern

Verified 2026-08-25 ('Daily Devops Digest', job <job-id>). Use when an LLM-mode
cron exists ONLY to run one script and relay its output — those burn API calls,
hallucinate tool-call syntax ("Model generated invalid tool call"), truncate on
output limits, and die when the model/provider blinks. A script needs no LLM.

## Diagnosis

`hermes cron list` / jobs.json shows recurring errors like:
- `Model generated invalid tool call: execute`
- `Response truncated due to output length limit`
- Connection errors on a schedule with no reason to need inference

If the prompt reads "Execute: python3 <script>. Then present the output" — it's
convertible. If the job actually REASONS over data (triage, drafting, decisions),
it stays LLM-mode.

## Conversion steps

1. **Fix the script first** — test-run it bare: `python3 ~/.hermes/scripts/<name>.py`.
   Common defect found this session: collectors ran but results were never written
   into the report string (header-only output). Read the whole script before trusting it.
2. **Script hygiene for no_agent mode** (see also memory gotcha): must default to its
   main/report action with empty argv; exit 0 ALWAYS (encode alarm states in output +
   nonzero exit only if delivery semantics want it); degrade failed collectors to
   'UNKNOWN' lines instead of crashing; self-contained env (no shell profile assumed).
3. **Convert**: cronjob(action='update', job_id=..., no_agent=true, script='<name>.py',
   prompt='') — script resolves relative to ~/.hermes/scripts/.
4. **Verify end-to-end**: cronjob(action='run', job_id=...) fires in background;
   confirm result block shows `Mode: no_agent`, `API calls: 0`, output matching a
   manual run. Next_run_at should reflect the normal schedule.

## Design notes for digest/monitor scripts

- Collectors: cron registry errors+staleness, kanban counts, peer-node GPU/disk via
  read-only ssh, service liveness via curl, artifact ages (e.g. <content-pipeline> per-channel
  content_history.json). Working example: ~/.hermes/scripts/daily_digest.py.
- Timestamps: treat naive timestamps as UTC explicitly before subtraction.
- Parsing multi-section remote output: wrap sections in sentinel markers
  (echo GSTART/DSTART) rather than positional line slicing.
- CRIT items → Telegram push via notify_telegram.py inside the script; WARN items
  ride the local delivery.
