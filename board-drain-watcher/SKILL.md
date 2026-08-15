---
name: board-drain-watcher
description: Wait for a Hermes kanban board's active (running/ready/todo) tasks to drain before running a follow-up step, so it never contends with real in-flight work on the same GPUs/workers. Exits 0 when clear, non-zero on timeout. Use to gate a calibration run, build, or maintenance pass behind the overnight fleet finishing.
---

# Board Drain Watcher

Watch a [Hermes Agent](https://github.com/NousResearch/Hermes-Agent) kanban
board until its active (running/ready/todo) tasks all finish, then exit.

Use it to gate a follow-up step — a calibration run, a build, a maintenance
pass — so it never competes with real in-flight fleet work on the same GPUs /
workers. Run it as a background process, then continue when it reports
`BOARD CLEAR`.

## Why

When a fleet of autonomous kanban workers grinds a queue, spawning another job
(like a benchmark or a deploy) at the wrong moment competes for the same
resources and slows everything. This watcher waits until the board is quiet.

## Usage

```bash
# Default: watch the 'overnight-build' board, check every 60s, timeout 2h
python3 watch_board_drain.py

# Custom board / cadence / timeout
WATCH_BOARD=myboard INTERVAL=30 TIMEOUT=3600 python3 watch_board_drain.py
```

Exit `0` = board drained (safe to proceed). Non-zero = timed out with tasks
still active.

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `WATCH_BOARD` | `overnight-build` | Board slug to watch |
| `INTERVAL` | `60` | Seconds between polls |
| `TIMEOUT` | `7200` | Give up after this many seconds |

## Requirements

- Hermes Agent with kanban boards on disk at `~/.hermes/kanban/boards/<slug>/`.