---
name: fleet-calibration
description: Measure what a kanban worker fleet can accurately reproduce on a regular basis. Runs a ladder of task types (trivial → deep-build) through the real gateway dispatch and scores each worker profile by whether it actually produced a verifiable artifact — catching the classic "faked done" failure (status=done but no output). Use when calibrating worker profiles, tuning a fleet, or proving a worker's reliability ceiling.
---

# Fleet Calibration

Measures what a [Hermes Agent](https://github.com/NousResearch/Hermes-Agent)
kanban worker fleet can *accurately reproduce*, on a repeatable basis. Instead
of trusting a worker's self-reported "done", every calibration task must write a
deterministic marker file into its workspace; the harness verifies the file
bytes on disk — so a worker that claims success but produces nothing (faked
completion) is caught and counted.

## Results

| Result | Meaning |
|--------|---------|
| `PASS` | status `done` **and** the marker file exists with expected content |
| `FAIL_NO_FILE` | status `done` but no artifact written (faked done) |
| `WRONG` | artifact present but wrong content |
| `STALE` | never finished within the timeout |
| `NO_CREATE` | task could not be created |

Plus runtime per task, written to a CSV you can diff across runs to track
fleet reliability over time.

## Complexity ladder

- **S1-trivial** — write one marker line
- **S2-simple** — marker + a trivial fact
- **S3-moderate** — marker + a small computation + a fact
- **S4-deep** — marker + a correct function + a short writeup
- **S5-build** — marker + a full runnable script + a tool list

## Requirements

- Hermes Agent with the kanban feature (`hermes kanban`).
- Worker profiles that claim and run kanban tasks (the gateway dispatches them
  automatically — the harness needs no daemon).

## Usage

```bash
# Validate the matrix without spawning anything
python3 fleet_calibration.py --dry-run

# Run a subset
python3 fleet_calibration.py --profiles builder --levels S3-moderate

# Run the full ladder
python3 fleet_calibration.py
```

Environment: `CALIBRATION_BOARD` (default `calibration`) picks the board.

## Configure for your fleet

Edit two lists at the top of the script:
- `PROFILES` — your worker profile names.
- `LADDER` — the ladder; each instruction must end with "write a file named
  `calibration_output.txt` in your workspace containing `<marker>`".

Marker is derived from the level name (`S3-moderate` → `MODERATE_OK`).