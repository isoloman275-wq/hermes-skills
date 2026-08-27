# Fleet routing lessons from the 2026-08-24 verifier-swarm wiring

## 1. Per-task model overrides do NOT hold against profile defaults

`hermes kanban set-model <task> <your-model> --provider ollama-m1` was accepted
("applies on next dispatch") but dispatch STILL resolved to the assignee
profile's own default (`<your-model> @ custom:hemi` → M2). The override is
advisory; the profile default wins at spawn time.

**Reliable fix = config-level stripping**: remove the banned host everywhere in
`~/.hermes/profiles/<name>/config.yaml`:
- top-level `model:` block (default + provider + any stale base_url line)
- `providers:` list entries (e.g. `ollama-m2:`)
- `custom_providers:` entries pointing at the host (e.g. `- name: Hemi`)
Then validate with `python3 -c "import yaml; yaml.safe_load(open(...))"`.

Verified result: after stripping all M2 refs from builder / marketing /
independent-verifier, the identical swarm ran clean on M1 with zero M2 traffic.

## 2. A user lineup change silently reverses routing assumptions

Between sessions the user changed the lineup: builder's default became M2's
<your-model> (not <your-model> as last known). Any fleet experiment must start by
reading the LIVE top-level `model:` block of every involved profile. Never trust
last session's roster or memory of who-runs-where.

## 3. Detecting and stopping banned-host routing mid-run

Symptom: worker crash-loops ~60s apart, log lines show
`base_url=http://<lab-host>:11434/v1` + HTTP 500 cudaMalloc OOM.
Stop sequence: `hermes kanban reclaim <worker_task>` FIRST (archive fails while
running) → kill orphaned run_agent PIDs → archive all swarm cards (worker,
verifier, synthesizer, root) → confirm `ps aux | grep run_agent` = 0.
The banned machine itself takes no harm — its OOM rejections mean nothing allocated.

## 4. Verified end-to-end swarm PASS (post-fix)

builder (<your-model> @ M1) produced artifact to spec → independent-verifier
(<your-model> @ M1, adversarial AGENT.md protocol) ran 366s, READ the artifact
with tools rather than trusting worker claims, completed with
`Gate: PASS` metadata → synthesizer queued → root DONE. Kanban swarm +
adversarial verifier profile = production-viable standing quality gate.
