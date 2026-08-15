---
name: m1-ollama-watchdog
description: Keep a Windows-hosted Ollama instance alive with a self-healing liveness watchdog. Detects a silently-dead Ollama (no process, nothing on :11434) and relaunches it detached, so dependent workers/fleets don't stall. Use when an Ollama server that other agents depend on keeps dying silently, or when you want to auto-heal an inference server.
---

# Ollama Liveness Watchdog

A self-healing watchdog for a Windows-hosted (or any) Ollama instance that
other workers/fleet agents depend on. If Ollama dies silently — no process,
nothing listening on port 11434 — the watchdog relaunches it detached, then
verifies recovery. This prevents a silent inference-server death from stalling
every dependent worker.

## Why this matters

A `curl /api/tags` to a dead Ollama returns nothing, but so does a *wedged*
server, and a freshly-restarted one during model cold-load can take 60-90s to
answer a generate probe. So this watchdog uses only the **fast `/api/tags`
check** (catches the "server absent" mode that actually takes a fleet down),
not a full model round-trip. It never pulls or deletes models — it only
restarts the already-installed `serve`.

## Install

1. Copy `ollama_watchdog.sh` to your scheduler host and `chmod +x`.
2. Edit the config block at the top:
   - `ENDPOINTS` — the base URLs to probe (LAN IP, WSL gateway, etc.).
   - `OLLAMA_EXE` — path to `ollama.exe` on the Windows host.
3. Wire it to a cron / scheduled task:
   ```
   */5 * * * * /path/to/ollama_watchdog.sh
   ```

## Usage

Run manually to check/relaunch once:

```bash
./ollama_watchdog.sh
```

Output:
- `OLLAMA OK (<ts>)` — healthy, exit 0.
- `OLLAMA DOWN ... relaunching` — was dead, relaunch attempted.
- `OLLAMA RECOVERED` — relaunch worked, exit 0.
- `OLLAMA RECOVERY FAILED` — needs manual intervention, exit 1.

## Notes

- On Windows hosts the relaunch sets `OLLAMA_HOST=0.0.0.0:11434` persistently so
  both the LAN and the WSL gateway can reach it after a reboot.
- Use the `/api/tags` probe for routine liveness; only escalate to a full
  generate round-trip (longer timeout) if you need to detect a wedged-but-"
  listening model.