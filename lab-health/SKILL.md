> Published from NZ1Labs internal tooling. Private LAN details replaced with `<lab-host>` / `<home>` placeholders.

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
M3 runs an Ollama instance on :11434 serving the **aux models** (`<your-model>` is the one to use; `<your-model> OOMs on the 4GB GTX 960). To verify the aux slot is alive, hit the Ollama HTTP API directly — this bypasses the flaky M3 SSH shell entirely. NOTE M3 IP is **<lab-host>** (was .9, changed 2026-08-04):
```bash
# models present
curl -s -m6 http://<lab-host>:11434/api/tags
# models actually resident in VRAM right now (usually empty between calls — see keepalive note)
curl -s -m8 http://<lab-host>:11434/api/ps
# live inference probe (MUST pass num_ctx — see pitfall below)
curl -s -m45 -X POST http://<lab-host>:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"model":"<your-model>","prompt":"ping","stream":false,"options":{"num_ctx":65536,"num_predict":20}}'
```
- **PITFALL — `2b-aux` context HANGS on the 4GB GTX 960 (corrected 2026-07-26).** Default `context_length` is 262,144 → hangs. But **65536 ALSO overflows the 4GB card**: at 65536 `api/ps` reports `size_vram` 6.6 GB (> 4 GB), so the model "loads" (api/ps shows it) but every generate HANGS even when warm (curl exit 28). The SAFE caps are **≤16384** (16384 ≈ 1.5s warm, 8192 ≈ 1.0s) — verified working. This is the usual root cause when "the aux slot never responds."
- **`/v1` (OpenAI-compatible) IGNORES `num_ctx` (and `think`).** Hermes's `ollama-m3` provider hits `http://<lab-host>:11434/v1`; passing `num_ctx` in the body does NOTHING (verified: sent 16384, loaded at 65536). To cap context for a `/v1` consumer, bake `PARAMETER num_ctx` into the Modelfile (`ollama create`) or use native `/api/chat` (which honors it). Per-request num_ctx only works on the native API.
- **SSH to M3 (port 22) is FIREWALL-BLOCKED** (connection timeout) — you cannot edit the M3 Modelfile remotely. `ollama create` must run ON M3 (Windows, where `ollama` is on PATH). Hand the user this same-name sequence:
  `ollama show --modelfile <your-model> | Out-File -Encoding utf8 Modelfile.txt` → edit to add `PARAMETER num_ctx 16384` (and `PARAMETER think false` if supported) → `ollama create <your-model>-c16 --file Modelfile.txt` → `ollama rm <your-model>` → `ollama create <your-model> --file Modelfile.txt` → `ollama rm <your-model>-c16`. (Drop `PARAMETER think false` if it errors — thinking is already off via Hermes `reasoning_effort: none`.)
- **M3 cold-load latency ~20s; set OLLAMA_KEEP_ALIVE=-1 to keep warm.** After a generate, `api/ps` shows no models loaded (default keepalive unloads). Every fresh call pays an ~11–20s load. If something calls the aux model repeatedly, set `OLLAMA_KEEP_ALIVE=-1` on M3 (systemd override / Windows service env) so `2b-aux` stays resident.
- **WSL2 reaches M3 even though WSL's own IP isn't whitelisted.** From WSL the box IP is 172.x (Hyper-V NAT), but outbound traffic is NAT'd through the Windows host <lab-host> — which is exactly the IP M3's Windows Firewall allows for :11434. So `curl` from WSL to M3 succeeds; don't mistake the 172.x IP for a block. (Correlates with the ICMP-vs-SSH trap: ping proves *a* host is up, but here the HTTP API is the real liveness test for the aux model.)
```

## Known Pitfalls

- **Cron model routing (CRITICAL — verified 2026-07-15)**: Any Hermes cron left with `provider: null` + a LOCAL model name (e.g. `<your-model>:latest`) FAILS every run with `400 '... is not a valid model ID'`. Root cause: config.yaml default `model.provider: custom` points at `base_url: https://openrouter.ai/api/v1` (OpenRouter). The scheduler ships the local name to OpenRouter, which rejects it. This silently breaks MULTIPLE crons at once — Lab Health Check Daily, the 3 TikTok Pipeline status crons (Morning/Midday/Evening), and the Web Design build-queue cron. The ONLY cron that works out-of-the-box is 'TikTok Analytics Daily Report' (it explicitly sets `provider: custom` + `base_url: http://<lab-host>:11434/v1`). FIX: for every local-model cron, set `provider: custom` + `base_url: http://<lab-host>:11434/v1` (M2 Ollama). Verify with `hermes cron list` — broken jobs show `last_error: RuntimeError: Error code: 400 ... 'not a valid model ID'`. NOTE: this is an OpenRouter rejection, NOT an Anthropic 'credit balance too low' error — the default provider is OpenRouter, not Anthropic.
- **M3 SSH can hang even with the wrapper (observed Jul 15 2026)**: ssh to M3 with a powershell -Command payload timed out at 60s while ping <lab-host> succeeded — the box is alive but its SSH shell session is unresponsive. Do not let M3 block the whole lab status check: run ping -c2 -W2 <lab-host> first; if ping is OK, report M3 as UP (ping), SSH stats unavailable and move on. M3 is aux Ollama only, non-critical, so missing its stats is acceptable during a routine health pass. Investigate the SSH hang separately, not mid-status-check.

- **M2 disk-percent quoting**: single-quoted SSH strings expand `$` literally, so variable assignments like `PERCENT=$(...)` never resolve. Use heredoc (`bash -s <<'EOF'`) to get proper shell expansion on the remote side.
- **WEDGED HOST signature (verified 2026-07-17, M2)**: If `ssh m2` (and even `ssh <ssh-user>@<lab-host>`) hangs at "Connection timed out during banner exchange" AND a raw TCP port scan shows the ports OPEN (22, 11434, 445, 3000, 5432, 5678, 8188) BUT every service behind them is non-responsive (curl to :11434/:3000/:5678 returns 000/empty) — the host is UP at kernel/network level but userspace is wedged (open sockets, dead services). Root cause is typically OOM during a heavy render (ComfyUI/Wan2.2 on the 3060s) or a hung filesystem mount (e.g. /mnt/storage NTFS) blocking sshd PAM/session spawn + Docker I/O. **Fix: hard-reboot M2** (PDU/IPMI/physical). SSH and API control are BOTH unavailable in this state, so there is no remote recovery — do not waste time retrying `ssh m2` or probing services. After reboot, re-run the `ssh m2 'bash -s'` health check to confirm recovery. NOTE: a plain `ping` to the IP will SUCCEED during this state (ICMP answered by kernel), which is what makes it misleading — ping alone does NOT mean services are healthy. Same signature later observed on M3 SSH (non-critical, left uninvestigated).

- **ICMP-vs-SSH address trap (CAUGHT 2026-07-17)**: `ping` can succeed against an IP that is NOT the target host. A raw IP (e.g. <lab-host>) answered ICMP but refused port 22 AND 11434 — it was a different device on the LAN, not M2. M2's real address is **<lab-host>**, reachable only via the `ssh m2` alias (user `<ssh-user>`, per `~/.ssh/config`), NOT by DNS hostname `m2` (DNS pointed `m2`→.15 but timed out; the alias is the source of truth). **Always use the SSH alias, never a guessed raw IP, and never treat a successful ping as proof the target host is healthy.** Ping proves *a* host is up; it does not prove the *intended* host is up or that its services are alive.

- **"Ports OPEN but services DEAD" wedge (CAUGHT 2026-07-17 — add to recovery runbook)**: When a port scan shows 22/445/11434/3000/5432/5678/8188 all OPEN but (a) `ssh m2` hangs at "Connection timed out during banner exchange" and (b) HTTP to those ports returns `000`/empty, the host kernel + UFW are up but the **userspace is wedged** — sshd accepts the TCP connection but never sends its SSH-2.0 banner; Docker/ComfyUI/Ollama hold sockets but never respond. Root causes observed/likely: OOM killing the container runtime or sshd worker (esp. after a ComfyUI/Wan2.2 render on the dual 3060s), or a hung filesystem mount (e.g. the NTFS `/mnt/storage` share) blocking PAM/session spawn. **This state is NOT fixable from M1** — no shell, no API control. Recovery = hard reboot M2 (PDU/IPMI/remote KVM or physical). After reboot, re-run the `ssh m2` health heredoc to confirm. See `references/wedge-recovery.md` for the exact triage sequence and the diagnostic that distinguishes this from a clean host-down.

- **Ollama binary update can drop the host**: running `curl ... install.sh | sh` to update Ollama on M2 reconfigures + restarts the systemd service and may **fully reboot M2** (not just the service). After it, M2 may be completely unreachable — no ping, no SSH, no API (full host-down, distinct from the "ports-open-services-dead" wedge). Any in-flight `ollama pull` gets SIGTERM (-15) when the host drops. **Recovery: hard reboot M2 (PDU/IPMI/physical), then re-run the pull** — Ollama caches partial downloads so it resumes. Verified 2026-07-18: `<your-model>` pull interrupted by an update-triggered drop; re-pull after reboot completed. Treat "update Ollama" as a host-affecting operation, not a safe in-place binary swap.

See `references/wedge-recovery.md` for the exact triage sequence, the wedge-vs-host-down distinction, and post-reboot root-cause checks.
- **M3 PowerShell wrapper required**: M3 SSH default shell is cmd.exe, not PowerShell. Commands like `Get-CimInstance`, `Get-Volume` will fail with *"not recognized as an internal or external command"*. Always wrap in `powershell -Command "..."`.

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
User flagged the 3:00 daily_pod <store> cron as "hasn't done a design all week and keeps
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

## Machine Registry
| Host | Address | OS / User | SSH alias | Role |
|------|---------|-----------|----------|------|
| M1 | local (WSL2 on Win11) | Ubuntu / <user> | — | Orchestrator, Hermes gateway (port 8644) |
| M2 | <lab-host> | Ubuntu / <ssh-user> | `ssh m2` | Inference server, **2x RTX 3060 = 24GB**, Ollama |
| M3 | **<lab-host>** (was .9) | Win10 LTSC IoT / admin | `ssh m3` | Worker node, GTX 960 4GB, aux Ollama |

NOTE: M3 IP changed to <lab-host> (verified 2026-08-04). M3 `:11434` answers HTTP even
though SSH port 22 stays firewalled/flaky — use the HTTP API for M3 model checks, SSH for
- From WSL, M1's *Windows-host* Ollama (<your-model>) is reached at
  **http://<wsl-gateway-ip>:11434** (the WSL gateway), NOT localhost (WSL has no Ollama of its own).

## M2 ComfyUI — Video-Only (image gen blocked)

M2 ComfyUI (8188) is configured for **Wan2.2 text-to-video only** — it has NO
SDXL/SD1.5 image checkpoint installed (verified 2026-07-18: checkpoint list empty).
Any static-image task (<store> POD artwork, thumbnails) is BLOCKED until an image
model is downloaded + placed in `<home>/ComfyUI/models/checkpoints/` (needs
SSH + ~6GB download, consent-gated). TikTok video renders work fine. See
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

## PATH TRAP — two `income-work` dirs (verified 2026-07-17)
There are TWO directories that look identical but are DIFFERENT filesystems:
- **`<home>/income-work/`** (WSL home) = the REAL one. All income-stream scaffolds live here (`<store>/`, `mobile-apps/`, `web-design/`, `trend-data/reports/`, etc.). The architecture doc + all real work reference this.
- **`<win-home>/income-work/`** (Windows C: mount) = a SEPARATE near-empty dir with the same folder names but NO scaffolds. Writing here strands the file where nothing reads it.
RULE: use `<home>/income-work/...` for income artifacts. Note `C:\pipeline` ↔ `/mnt/c/pipeline` ARE the same FS (WSL mounts C:), so those are interchangeable — but `income-work` is ONLY under `<home>`, never under `<win-home>`. `ls -la` before writing if unsure.

| Container | Image | Host Port | Notes |
|-----------|-------|-----------|-------|
| open-webui | ghcr.io/open-webui/open-webui:main | 3000→8080 | Chat UI for Ollama |
| n8n | n8nio/n8n | 5678→5678 | Workflow automation |
| postgres | postgres:16 | 5432→5432 | Used by n8n. Binds 0.0.0.0 — UFW handles scoping |

ComfyUI runs as a **native process** (not Docker): `<home>/start_comfyui.sh` → python3 main.py on port 8188, pinned to GPU 1 (`--cuda-device 1`).

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

## Maintenance Schedule (NZT)
- 02:00–06:00 Batch maintenance window (disk cleanup, log rotation, backups) — coincides with ComfyUI video gen, no inference conflict
- Every 6h: Lab health check cron
- Daily 03:00: M2 disk cleanup (at 86% — critical threshold)
- Daily 05:00: Hermes config backup
- Sunday 03:00: Security port scan vs baseline
See `references/maintenance-schedule.md` for cron scripts and job details.
See `references/security-audit-july2026.md` for full audit findings and remediation commands.
