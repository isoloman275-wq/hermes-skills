---
name: lab-health
description: Full lab health check - M1, M2, M3 reachability, Ollama status, disk space, load. Use when asked "is everything ok", "lab status", "health check".
---
# Lab Health Check

Three-machine home lab setup: M1 (orchestrator), M2 (inference), M3 (worker).

## Health Check Commands

### M1 (local WSL)
```bash
nproc && free -h | head -2 && df -h / | tail -1
# Also check Hermes gateway health
curl -s http://localhost:8644/health || echo "Gateway not responding"
```

### M2 — full system check via SSH (single command)

Use `m2` alias (NOT raw IP — key auth is per-user). Pipe through bash explicitly for reliable quoting:

```bash
ssh m2 'bash -s' <<'EOF'
uptime
df -h / | tail -1
PERCENT=$(df -h / | tail -1 | awk "{print \$5}" | tr -d "%")
echo "Disk: ${PERCENT}%"
[ "$PERCENT" -gt 85 ] && echo "WARN: Disk >85%" || true
echo "---GPU0---"
nvidia-smi --id=0 --query-gpu=index,memory.used,memory.free,temperature.gpu,power.draw --format=csv,noheader
echo "---GPU1---"
nvidia-smi --id=1 --query-gpu=index,memory.used,memory.free,temperature.gpu,power.draw --format=csv,noheader
echo "---OLLAMA---"
curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -m json.tool 2>/dev/null | head -40 || ollama ps
EOF
```

### M3 (Windows) — SSH first, ping fallback

M3 SSH drops into cmd.exe by default — PowerShell cmdlets fail without explicit wrapper. Always pipe through `powershell -Command "..."`:

```bash
ssh m3 'powershell -Command "Get-CimInstance Win32_OperatingSystem | Select-Object @{N=\"FreeMemGB\";E={[math]::Round($_.FreePhysicalMemory/1MB)}}; Get-Volume -DriveLetter C | Select-Object @{N=\"UsedPct\";E={[math]::Round(100*($_.Size-$_.SizeRemaining)/$_.Size)}}, @{N=\"FreeGB\";E={[math]::Round($_.SizeRemaining/1MB)}}"'
# SSH flaky: fall back to ping <lab-host> (M3 current IP; was .9 before 2026-08-04)

### M3 aux Ollama model — reachability via the HTTP API (NOT SSH)
M3 runs an Ollama instance on :11434 serving the **aux models** (`<your-model> is the one to use; `<your-model> OOMs on the 4GB GTX 960). To verify the aux slot is alive, hit the Ollama HTTP API directly — this bypasses the flaky M3 SSH shell entirely. NOTE M3 IP is **<lab-host>** (was .9, changed 2026-08-04):
```bash
# models present
curl -s -m6 http://<lab-host>:11434/api/tags
# models actually resident in VRAM right now (usually empty between calls — see keepalive note)
curl -s -m8 http://<lab-host>:11434/api/ps
# live inference probe (MUST pass num_ctx — see pitfall below)
curl -s -m45 -X POST http://<lab-host>:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"<your-model>
```
- **PITFALL — `2b-aux` context HANGS on the 4GB GTX 960 (corrected 2026-07-26).** Default `context_length` is 262,144 → hangs. But **65536 ALSO overflows the 4GB card**: at 65536 `api/ps` reports `size_vram` 6.6 GB (> 4 GB), so the model "loads" (api/ps shows it) but every generate HANGS even when warm (curl exit 28). The SAFE caps are **≤16384** (16384 ≈ 1.5s warm, 8192 ≈ 1.0s) — verified working. This is the usual root cause when "the aux slot never responds."
- **`/v1` (OpenAI-compatible) IGNORES `num_ctx` (and `think`).** Hermes's `ollama-m3` provider hits `http://<lab-host>:11434/v1`; passing `num_ctx` in the body does NOTHING (verified: sent 16384, loaded at 65536). To cap context for a `/v1` consumer, bake `PARAMETER num_ctx` into the Modelfile (`ollama create`) or use native `/api/chat` (which honors it). Per-request num_ctx only works on the native API.
- **M3 SSH port 22 is OPEN but UNAUTHORIZED (corrected 2026-08-21)** — a raw `/dev/tcp` probe shows port 22 OPEN, but the WSL key (`<user>`) gets `Permission denied (publickey)`. It is an AUTH gap, NOT a firewall block — add the WSL pubkey to M3's `~/.ssh/authorized_keys` (or run from a user whose key is enrolled) to drive M3. Until then, model checks use the :11434 HTTP API. `ollama create` must still run ON M3 (Windows, where `ollama` is on PATH). Hand the user this same-name sequence:
  `ollama show --modelfile <your-model> | Out-File -Encoding utf8 Modelfile.txt` → edit to add `PARAMETER num_ctx 16384` (and `PARAMETER think false` if supported) → `ollama create <your-model> --file Modelfile.txt` → `ollama rm <your-model> → `ollama create <your-model> --file Modelfile.txt` → `ollama rm <your-model> (Drop `PARAMETER think false` if it errors — thinking is already off via Hermes `reasoning_effort: none`.)
- **M3 cold-load latency ~20s; set OLLAMA_KEEP_ALIVE=-1 to keep warm.** After a generate, `api/ps` shows no models loaded (default keepalive unloads). Every fresh call pays an ~11–20s load. If something calls the aux model repeatedly, set `OLLAMA_KEEP_ALIVE=-1` on M3 (systemd override / Windows service env) so `2b-aux` stays resident.
- **WSL2 reaches M3 even though WSL's own IP isn't whitelisted.** From WSL the box IP is 172.x (Hyper-V NAT), but outbound traffic is NAT'd through the Windows host <lab-host> — which is exactly the IP M3's Windows Firewall allows for :11434. So `curl` from WSL to M3 succeeds; don't mistake the 172.x IP for a block. (Correlates with the ICMP-vs-SSH trap: ping proves *a* host is up, but here the HTTP API is the real liveness test for the aux model.)
```

## HARD RULES — EPISTEMIC DISCIPLINE (user-emphatic, 2026-08-20)

These are non-negotiable. Violating them is the #1 trust-destroyer (user verbatim: "stop answering from assumption, ever").

1. **NEVER answer from assumption.** Before stating any fact about system behavior, model capability, config value, or lab state, VERIFY it against a live source (SSH/curl/`hermes cron list`/reading the actual file) OR the authoritative documentation. If you don't know, say "I don't know" and go find it. A confident-sounding guess presented as ground truth is a failure, even if it happens to be right.
   - Corrollary: if the question is about a SYSTEM's documented behavior (context limits, config keys, tool semantics), **LOAD THE RELEVANT SKILL/DOC FIRST** (e.g. `hermes-agent` references for Hermes config). Do not answer from memory of what you think the docs say. The user explicitly called this out: "you don't know your own documentation?" — load it, read it, then answer.
2. **CROSS-CHECK THE SCHEDULE before reporting machine/lab status.** A GPU/load reading ALONE does not answer "is the machine busy" or "is there a free slot." You MUST also pull the live cron timetable (`hermes cron list`) and reconcile: what job is *supposed* to be running now vs. what the GPU is actually doing. A 100% GPU could be a scheduled render, a manual run, or a wedged process — only the timetable tells you which, and only the reconciliation tells you if there's a collision or a genuine free window. User correction: "why aren't you cross checking timetable." Reporting raw `nvidia-smi` without the cron cross-reference is an incomplete answer.
   - When a machine can't be probed (e.g. M3 SSH `Permission denied`), state it as **UNKNOWN**, never as "idle" or "down." Absence of evidence is not evidence of absence.

## Known Pitfalls

- **Cron model routing (CRITICAL — verified 2026-07-15)**: Any Hermes cron left with `provider: null` + a LOCAL model name (e.g. `<your-model> FAILS every run with `400 '... is not a valid model ID'`. Root cause: config.yaml default `model.provider: custom` points at `base_url: https://openrouter.ai/api/v1` (OpenRouter). The scheduler ships the local name to OpenRouter, which rejects it. This silently breaks MULTIPLE crons at once — Lab Health Check Daily, the 3 <content-pipeline> Pipeline status crons (Morning/Midday/Evening), and the Web Design build-queue cron. The ONLY cron that works out-of-the-box is '<content-pipeline> Analytics Daily Report' (it explicitly sets `provider: custom` + `base_url: http://<lab-host>:11434/v1`). FIX: for every local-model cron, set `provider: custom` + `base_url: http://<lab-host>:11434/v1` (M2 Ollama). Verify with `hermes cron list` — broken jobs show `last_error: RuntimeError: Error code: 400 ... 'not a valid model ID'`. NOTE: this is an OpenRouter rejection, NOT an Anthropic 'credit balance too low' error — the default provider is OpenRouter, not Anthropic.
- **SELF-HEAL BLIND SPOT (verified 2026-08-22 — THE reason "self-healing" reported ok while crons died for 6-7 days).** The `cron_self_heal.py` only checked `last_status == "error"` + `last_fire_error`. An enabled cron that **silently stops firing** (last run 6 days ago, but `last_status` still says "ok" from its last successful run) is INVISIBLE to that check — it reports green while the job is dead. FIX: self-heal MUST also compute `last_run_at` age vs the cron's interval and flag STALE if `age > 2x interval` (weekly crons: miss 2-3 runs). Reference: `references/fleet-self-heal.md` for the working patch + the fleet-worker reap watchdog. Also: a self-heal cron that itself only checks flags is worthless — it must verify *process state* (wedged workers) and *delivered output*, not just registry status. User verbatim: "self improving and self healing yesterday complete waste of time" — because it checked flags, not reality.
- **FLEET WORKER WEDGE = <content-pipeline> KILLER (verified 2026-08-22).** The overnight kanban fleet spawns workers (`hermes ... work kanban task t_xxx`) that sometimes don't exit. A wedged worker holds M2's <your-model> slot → <content-pipeline>'s 07:00 script-gen hits 404/collision → post skipped. EVERY DAY. Fix pattern (working): a no_agent watchdog cron (`*/15 23,0,1,2,3,4,5,6 * * *`) that (a) kills any `work kanban task` process alive >90 min, and (b) at 06:50 unconditionally kills ALL fleet workers so <content-pipeline> owns M2. Plus the decomposer self-limits: never queue past 05:00. This is the only reliable guard — "pause/reassign" doesn't work; kill the zombie. Reference: `references/fleet-self-heal.md`.

- **M2 disk-percent quoting**: single-quoted SSH strings expand `$` literally, so variable assignments like `PERCENT=$(...)` never resolve. Use heredoc (`bash -s <<'EOF'`) to get proper shell expansion on the remote side.
- **WEDGED HOST signature (verified 2026-07-17, M2)**: If `ssh m2` (and even `ssh <ssh-user>@<lab-host>`) hangs at "Connection timed out during banner exchange" AND a raw TCP port scan shows the ports OPEN (22, 11434, 445, 3000, 5432, 5678, 8188) BUT every service behind them is non-responsive (curl to :11434/:3000/:5678 returns 000/empty) — the host is UP at kernel/network level but userspace is wedged (open sockets, dead services). Root cause is typically OOM during a heavy render (ComfyUI/Wan2.2 on the 3060s) or a hung filesystem mount (e.g. /mnt/storage NTFS) blocking sshd PAM/session spawn + Docker I/O. **Fix: hard-reboot M2** (PDU/IPMI/physical). SSH and API control are BOTH unavailable in this state, so there is no remote recovery — do not waste time retrying `ssh m2` or probing services. After reboot, re-run the `ssh m2 'bash -s'` health check to confirm recovery. NOTE: a plain `ping` to the IP will SUCCEED during this state (ICMP answered by kernel), which is what makes it misleading — ping alone does NOT mean services are healthy. Same signature later observed on M3 SSH (non-critical, left uninvestigated).

- **ICMP-vs-SSH address trap (CAUGHT 2026-07-17)**: `ping` can succeed against an IP that is NOT the target host. A raw IP (e.g. <lab-host>) answered ICMP but refused port 22 AND 11434 — it was a different device on the LAN, not M2. M2's real address is **<lab-host>**, reachable only via the `ssh m2` alias (user `<ssh-user>`, per `~/.ssh/config`), NOT by DNS hostname `m2` (DNS pointed `m2`→.15 but timed out; the alias is the source of truth). **Always use the SSH alias, never a guessed raw IP, and never treat a successful ping as proof the target host is healthy.** Ping proves *a* host is up; it does not prove the *intended* host is up or that its services are alive.

- **"Ports OPEN but services DEAD" wedge (CAUGHT 2026-07-17 — add to recovery runbook)**: When a port scan shows 22/445/11434/3000/5432/5678/8188 all OPEN but (a) `ssh m2` hangs at "Connection timed out during banner exchange" and (b) HTTP to those ports returns `000`/empty, the host kernel + UFW are up but the **userspace is wedged** — sshd accepts the TCP connection but never sends its SSH-2.0 banner; Docker/ComfyUI/Ollama hold sockets but never respond. Root causes observed/likely: OOM killing the container runtime or sshd worker (esp. after a ComfyUI/Wan2.2 render on the dual 3060s), or a hung filesystem mount (e.g. the NTFS `/mnt/storage` share) blocking PAM/session spawn. **This state is NOT fixable from M1** — no shell, no API control. Recovery = hard reboot M2 (PDU/IPMI/remote KVM or physical). After reboot, re-run the `ssh m2` health heredoc to confirm. See `references/wedge-recovery.md` for the exact triage sequence and the diagnostic that distinguishes this from a clean host-down.

- **Ollama binary update can drop the host**: running `curl ... install.sh | sh` to update Ollama on M2 reconfigures + restarts the systemd service and may **fully reboot M2** (not just the service). After it, M2 may be completely unreachable — no ping, no SSH, no API (full host-down, distinct from the "ports-open-services-dead" wedge). Any in-flight `ollama pull` gets SIGTERM (-15) when the host drops. **Recovery: hard reboot M2 (PDU/IPMI/physical), then re-run the pull** — Ollama caches partial downloads so it resumes. Verified 2026-07-18: `<your-model> pull interrupted by an update-triggered drop; re-pull after reboot completed. Treat "update Ollama" as a host-affecting operation, not a safe in-place binary swap.

See `references/wedge-recovery.md` for the exact triage sequence, the wedge-vs-host-down distinction, and post-reboot root-cause checks.
- **M3 PowerShell wrapper required**: M3 SSH default shell is cmd.exe, not PowerShell. Commands like `Get-CimInstance`, `Get-Volume` will fail with *"not recognized as an internal or external command"*. Always wrap in `powershell -Command "..."`.

- **M3 OLLAMA INSTALL ROOT CAUSE + FIX (verified 2026-08-21)**: A manual `ollama.exe` copy to `C:\Program Files\Ollama\` is INCOMPLETE — Ollama needs `C:\Program Files\Ollama\lib\ollama\llama-server.exe` (the actual inference backend). Without it, the service starts, lists models via `/api/tags`, but falls back to **CPU** (0 B VRAM) or dies on load with `failure during llama-server GPU discovery: llama-server binary not found`. Symptom seen: service "UP" but every `/api/chat` returns `invalid character` / connection drop, GPU shows 0 B VRAM. **FIX**: copy the full `lib\` tree from the install zip (`C:\ollama_tmp\lib` → `C:\Program Files\Ollama\lib`) before first launch. ALSO: launching via `Start-Process` / `cmd /c start` from an SSH session is **session-bound** — the process dies when the SSH connection's process tree tears down, so Ollama "disappears" between checks. **PERSISTENCE FIX**: register a scheduled task running a `.bat` wrapper (`cd /d "C:\Program Files\Ollama"` then `"C:\Program Files\Ollama\ollama.exe" serve`) as `SYSTEM` with `/SC MINUTE /MO 5` (watchdog — restarts within 5 min if it dies). The `.bat` MUST use `cd /d` (working dir matters) and be invoked via `schtasks /Run /TN OllamaServe` (not a manual Start-Process). Full command sequence + verification in `references/m3-ollama-install-fix.md`.

- **M3 Ollama firewall + WSL reachability (verified 2026-08-21)**: WSL→M3 `:11434` is unreliable even after adding the `Ollama-In-11434` inbound rule — WSL's NAT (172.x) may not match M3's Windows Firewall scoping (which allows <lab-host>). The HTTP API works FROM M3 itself (localhost) reliably; cross-node from WSL is best-effort. For agent use, prefer running Ollama checks / inference ON M3 (SSH + localhost), not curling from WSL. When WSL curl to M3 returns empty, do NOT conclude M3 is down — verify via `ssh m3 'powershell -Command "(Invoke-RestMethod http://localhost:11434/api/tags).models.name"'`.

## Warning Thresholds
| Metric | WARN at | CRITICAL at |
|--------|---------|-------------|
| Disk / partition | >85% | >92% |
| M2 per-GPU VRAM | >90% (unless ComfyUI/Wan rendering) | >100% (OOM risk) |
| GPU temperature | >75°C | >85°C |
| M1 CPU load | >6 (8 cores) | >8 |
| RAM usage | >80% | >90% |

## Reporting Format
Report each machine as **OK** / **WARN** / **CRIT** with one line each:
```
M1 (orchestrator): OK — 72% RAM, disk 45%, gateway responding
M2 (inference): WARN — GPU0 at 92% VRAM, ComfyUI rendering active, disk 68%
M3 (worker): OK — SSH reachable, 5.2/16GB free RAM
```

## PITFALL — a cron / service reports "ok" but produces NOTHING (2026-08-04)
`last_status: ok` on a cron, or a running service, does NOT mean output landed.
User flagged the 3:00 <pod-cron> <store> cron as "hasn't done a design all week and keeps
erroring" — the cron registry said `ok`, and the REAL answer was both subtler and useful:
it WAS generating designs but writing to `<store>/daily/` (not `<store>/designs/`), and its
report showed `"drafts_pushed": []` + `"DRAFTS ONLY — awaiting user sign-off"` — i.e. it
was gated on publish, not broken. When the user suspects a cron is doing nothing:
- CONFIRM REAL OUTPUT, not status: `find <workdir> -newermt <thisweek> -type f
  (designs/*.png, daily/*.json)` to see actual produced artifacts and their dates.
- Check the work-report sidecar (e.g. `daily/report.json`) for `picks[]` vs
  `drafts_pushed[]` — "picks but no push" = gated-on-approval, a governance state, not an error.
- Check MODEL WARMTH for a suspected-idle model: `curl /api/ps` shows what is resident.
  A model that "should" serve a role but never appears warm is effectively not firing
  (this is how a dead/rarely-used model, and a dormant role, get exposed).
- 2b-aux on M3 was resident as 4b only — 2b-aux never warm = the aux role it backs is
  itself rarely/never exercising. Model warmth is a direct proxy for real usage.
LESSON: services must be monitored for DELIVERED WORK, not just process/alive status.
Surface silent breakage (produced nothing, model idle, gated output) early rather than
waiting for a deep-dive. This is the "lab integrity monitor" the user asked for — it
should check every cron's actual output + model residence on a schedule and alert on drift.
Full design intent: `references/lab-integrity-monitor.md`.

## M2 ARCHITECTURE (CANONICAL — NEVER call M2 single-VRAM)
M2 = **2 × RTX 3060, 12GB each = 24GB total**. `nvidia-smi` shows GPU0 AND GPU1.
**BOTH GPUs are used for LLM inference — models SPAN BOTH GPUs (24GB pooled), never
pinned to one card** (pinning to one card wastes the server). ComfyUI runs on GPU0 only
(`CUDA_VISIBLE_DEVICES=0` in start_comfyui.sh) but is NOT always active — GPU1 stays free
for inference when not rendering. HARD RULES (user-emphatic, 2026-08-04):
- When ComfyUI needs the GPUs for a render, LLMs are UNLOADED/REMOVED from VRAM before
  the render — model use is out of the question while ComfyUI renders.
- **10-min buffer before ch1 render slots**: cutoff 10 min before each render so models
  unload cleanly and no sub-agent interferes: morning 06:50/07:00, midday 11:20/11:30,
  evening 17:50/18:00 (NZT). During those blocked windows M2 is off-limits for agents.
- Full canonical model settings table: `references/lab-model-matrix.md`.

## Machine Registry (verified live 2026-08-11 — hardware + GPU measured from runtime)
| Host | Address | OS / User | SSH alias | Role / Hardware |
|------|---------|----------|-----------|------|
| M1 | local (WSL2 on Win11) | Ubuntu / <user> | — | Orchestrator, Hermes gateway (8644). **GPU: AMD Radeon RX 5700 XT 8GB** (driver 32.0.21043.5001), **Ollama backend = VULKAN** (server.log: Vulkan0 model 4812MiB + KV 4096MiB). Model <your-model> (5.6GB, 131072 ctx, temp 0.6). 8 cores / 23GB RAM. Ollama from WSL = **<wsl-gateway-ip>:11434**; LAN IP **<lab-host>**. |
| M2 | <lab-host> | Ubuntu / <ssh-user> | `ssh m2` | Inference server, **2× RTX 3060 = 24GB pooled** (nvidia-smi GPU0+GPU1, both 12288MiB; Ollama spans BOTH), Ollama. ComfyUI GPU0 only (Wan renders). Models: <your-model> (21.2GB, 232000 ctx, num_gpu 41), <your-model> (17.7GB, 132K/135168 ctx, vision-capable, num_gpu 66, q4_0 KV, reasoning off via think:false); also gemma4. Vision models LIVE here. Hindsight MCP :8888 |
| M3 | **<lab-host>** (was .9) | Win10 LTSC IoT / admin | `ssh m3` | Worker node, **GTX 960 4GB** (SSH:22 OPEN at TCP but WSL key unauth — 'Permission denied'; add WSL pubkey to authorized_keys; use :11434 HTTP for model checks). Models <your-model> (1.9GB, resident 2.4GB VRAM), <your-model> (3.4GB) |

NOTE: M3 IP changed to <lab-host> (verified 2026-08-04). M3 `:11434` answers HTTP even
though SSH port 22 stays firewalled/flaky — use the HTTP API for M3 model checks, SSH for
it fails. Also from WSL, M1's *Windows-host* Ollama (<your-model> is reached at
**http://<wsl-gateway-ip>:11434** (the WSL gateway), NOT localhost (WSL has no Ollama of its own).
VISION on M1 uses the VULKAN backend (NOT CPU-only, NOT ROCm) — pick a small Vulkan-fit model
(moondream ~1.8GB or llava:7b ~4.7GB) to stay inside the 8GB card with room for context.

## M2 ComfyUI — Video-Only (image gen blocked)

M2 ComfyUI (8188) is configured for **Wan2.2 text-to-video only** — it has NO
SDXL/SD1.5 image checkpoint installed (verified 2026-07-18: checkpoint list empty).
Any static-image task (<store> POD artwork, thumbnails) is BLOCKED until an image
model is downloaded + placed in `/<home>/ComfyUI/models/checkpoints/` (needs
SSH + ~6GB download, consent-gated). <content-pipeline> video renders work fine. See
`references/comfyui-m2-models.md` for the enable procedure + quick-check command.

## M2 Ollama Config Location
Systemd override at `/etc/systemd/system/ollama.service.d/override.conf`. Current settings (as of July 2026):
- `OLLAMA_KEEP_ALIVE=-1` (models stay warm forever)
- `OLLAMA_HOST=0.0.0.0:11434`
- `OLLAMA_CONTEXT_LENGTH=65536`
- `OLLAMA_FLASH_ATTENTION=1`
- `OLLAMA_KV_CACHE_TYPE=q4_0` (REQUIRED at 65K context — without it, KV cache overflows VRAM)
- `OLLAMA_NUM_PARALLEL=3` (added July 13 — takes effect on next Ollama restart)
- `OLLAMA_MAX_LOADED_MODELS=2` (added July 13 — takes effect on next Ollama restart)

## M2 Docker Services
M2 runs several services as Docker containers — ports that look like bare services are NOT:
- Port 3000 → `open-webui` container
- Port 5432 → `postgres:16` container
- Port 5678 → `n8n` container
Reconfiguring bind address requires Docker compose changes, not service config files.

## M2 Sudo Access
<ssh-user> has NOPASSWD sudo via `/etc/sudoers.d/<ssh-user>-nopasswd` (added July 13 2026). SSH sudo commands work without password piping.

## M1 WSL Config

All major services on M2 run as Docker containers, not native processes. This matters for config changes — postgresql.conf does NOT exist in /etc/postgresql, it's inside the container.

## PATH TRAP — two `<income-work-dir>` dirs (verified 2026-07-17)
There are TWO directories that look identical but are DIFFERENT filesystems:
- **`/<home>/<income-work-dir>/`** (WSL home) = the REAL one. All income-stream scaffolds live here (`<store>/`, `mobile-apps/`, `web-design/`, `trend-data/reports/`, etc.). The architecture doc + all real work reference this.
- **`/mnt/c/Users/Admin/<income-work-dir>/`** (Windows C: mount) = a SEPARATE near-empty dir with the same folder names but NO scaffolds. Writing here strands the file where nothing reads it.
RULE: use `/<home>/<income-work-dir>/...` for income artifacts. Note `C:\pipeline` ↔ `/mnt/c/pipeline` ARE the same FS (WSL mounts C:), so those are interchangeable — but `<income-work-dir>` is ONLY under `<home>`, never under `/mnt/c/Users/Admin`. `ls -la` before writing if unsure.

| Container | Image | Host Port | Notes |
|-----------|-------|-----------|-------|
| open-webui | ghcr.io/open-webui/open-webui:main | 3000→8080 | Chat UI for Ollama |
| n8n | n8nio/n8n | 5678→5678 | Workflow automation |
| postgres | postgres:16 | 5432→5432 | Used by n8n/<project-dir>. Binds 0.0.0.0 — UFW handles scoping |

ComfyUI runs as a **native process** (not Docker): `/<home>/start_comfyui.sh` → python3 main.py on port 8188, pinned to GPU 1 (`--cuda-device 1`).

Ollama runs as a **systemd service** (not Docker). Override at `/etc/systemd/system/ollama.service.d/override.conf`.

To modify postgres config: `sudo docker exec -it postgres psql -U postgres` or exec into container — do NOT look for /etc/postgresql on the host.

## M2 Security Posture (post July 2026 hardening)

UFW active. Rules:
- Port 22 (SSH): <lab-host>/24 only
- Port 11434 (Ollama): <lab-host>/24 only
- Port 5678 (n8n): <lab-host>/24 only
- Port 8188 (ComfyUI): <lab-host>/24 only
- Port 3000 (Open WebUI): <lab-host>/24 only
- All else: denied

SSH: password auth disabled, AllowUsers <ssh-user>, max 3 attempts.
fail2ban: active, watching sshd jail, 1h ban / 5 attempts in 10m.

## M3 Security Posture (post July 2026 hardening)

Windows Firewall enabled on all profiles.
- Ollama port 11434: restricted to <lab-host> (M1) only
- Remote Assistance: disabled
- RustDesk: disabled
- Network Discovery (SSDP/UPnP/mDNS/LLMNR): disabled
## Network Posture — ACTUAL STATE (verified Jul 14 2026)

All three machines on isolated private LAN (<lab-host>/24).

**M2 — UFW ACTIVE (hardened Jul 13).** Services scoped to LAN:
- Ollama API :11434, n8n :5678, ComfyUI :8188, Open WebUI :3000 — all restricted to <lab-host>/24
- PostgreSQL :5432 and Samba :139/:445 UFW-whitelisted for LAN access
- SSH: password auth disabled, AllowUsers <ssh-user>, MaxAuthTries 3
- fail2ban active: 1h ban, 5 attempts in 10m, watching sshd jail

**M3 — Windows Firewall ON.** Ollama scoped to M1 IP (<lab-host>) only. Remote Assistance, RustDesk disabled.

**M1 — Clean.** Only port 8644 (Hermes gateway) exposed on 0.0.0.0.

SSH aliases in `~/.ssh/config` on M1: `m2` (<ssh-user>@<lab-host>), `m3` (admin@<lab-host>).

- **Ollama `--load-mode` 500 on <your-model> (VERIFIED FIX 2026-08-20)**: Symptom: every `POST /api/generate` to `<your-model> returns `HTTP 500` → `error: invalid argument: --load-mode`. Root cause: the official <your-model> model ships `draft_num_predict 4` (MTP speculative decoding); Ollama's scheduler emits `--load-mode none --spec-type draft-mtp` to the bundled `llama-server`, which (on 0.32.14) rejects the flag. Confirmed via ollama/ollama#17790 (maintainer: default `draft_num_predict` is 4 for <your-model>). **DO NOT fix by recreating the model without `draft_num_predict`** — `ollama create` copies ~17GB and will fill a 76%-full `sda2` (you'll hit "no space left on device" mid-copy, and the new tag fails to register). The correct fix is a **binary-only Ollama upgrade**: download `ollama-linux-amd64.tar.zst` for the newer release (0.32.15 was published 2026-08-19, one day after 0.32.14), stop the service, extract over `/usr/local/bin/ollama` + `/usr/local/lib/ollama`, restart, re-test `curl /api/generate`. No model blobs touched, no store move. VERIFIED: after upgrade, `/api/generate` returns HTTP 200. See `references/ollama-load-mode-fix.md` for the exact commands + the GitHub-issue trail. LESSON: when a generate 500s with a flag-error, check whether the *scheduler* and the *bundled llama-server* are version-skewed (grep both binaries for the flag string) before touching models or disk.

## PITFALL — config.yaml model default ≠ actual session model (2026-08-17)
`config.yaml`'s `model.default` + `model.provider` is the GLOBAL fallback, but per-session or UI-level overrides can differ. The Hermes desktop app may have set a different model when this conversation started. **Never assume config.yaml reflects what's actually running this turn.** To verify ground truth: check the gateway agent logs (`~/.hermes/logs/agent.log`) for lines like `API call #N: model=<name> provider=<provider>` — these are the actual API requests fired by the current session. The session header shown at the top of a conversation also reports the model, but the log is the only verified source.

## PITFALL — don't probe lab machines for general model questions (2026-08-17)
When asked about a model that isn't in our lab roster (lab-model-matrix.md), **do NOT start by SSHing into M2/M3 or curling Ollama APIs**. Most models live on cloud providers (OpenRouter, etc.) and aren't pulled locally. Search externally first (HuggingFace, OpenRouter catalog, vendor docs). Only probe lab machines when the question is specifically about whether a model exists ON OUR BOXES. User correction: "why we checking m2?" — this pattern wastes cycles and annoys the user.

## PITFALL — stale reachability notes ('SSH blocked/firewalled') LIE (corrected 2026-08-21)
Memory/notes that a lab machine is 'SSH firewalled/blocked' go STALE and were FALSE this session. A live `/dev/tcp` probe + actual `ssh` connection is the only truth:
- **M2 SSH IS reachable from WSL** as `<ssh-user>@<lab-host>` (key auth works; `ssh m2` alias resolves there). The agent CAN drive M2 directly (run commands, SCP artifacts) — do not repeat stale 'SSH blocked' claims.
- **M3 port 22 is OPEN** (TCP) but the WSL key is unauthenticated (see M3 row). Not firewalled.
- ALWAYS re-probe (`(exec 3<>/dev/tcp/HOST/22) && echo OPEN`; then a real `ssh` auth attempt) before stating a machine is unreachable. A prior 'blocked' note is a hypothesis, not ground truth.

## PITFALL — stage large artifacts to M2 `/mnt/storage`, not root (2026-08-21)
M2 root `/dev/sda2` is ~89% full (12G free) — it CANNOT hold a 15G model. M2 has a SECOND disk `/mnt/storage` (`/dev/sdb2`, ~167G free) exposed via Samba AND reachable over SSH. To stage a base/model to M2: `scp -r <local> <ssh-user>@<lab-host>:/mnt/storage/<name>/` (no Samba/smbclient needed). Always `df` the target first (disk-check rule). The training venv is `/<home>/terea-venv`; point trainers at `/mnt/storage` paths so they run on M2 without re-downloading.

## Maintenance Schedule (NZT)
- 02:00–06:00 Batch maintenance window (disk cleanup, log rotation, backups) — coincides with ComfyUI video gen, no inference conflict
- Every 6h: Lab health check cron
- Daily 03:00: M2 disk cleanup (at 86% — critical threshold)
- Daily 05:00: Hermes config backup
- Sunday 03:00: Security port scan vs baseline
See `references/maintenance-schedule.md` for cron scripts and job details.
See `references/security-audit-july2026.md` for full audit findings and remediation commands.
