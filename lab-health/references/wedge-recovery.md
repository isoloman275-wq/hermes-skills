# M2 "Ports OPEN / Services DEAD" Wedge — Triage & Recovery

Observed 2026-07-17 during a lab health check. M2 (<lab-host>, user `<ssh-user>`, alias `ssh m2`)
appeared online by ping but was actually wedged.

## Symptom signature
- `ping <lab-host>` → 0% loss, sub-ms latency (host/kernel alive, on LAN).
- TCP port scan: 22, 445, 11434, 3000, 5432, 5678, 8188 ALL OPEN.
- `ssh m2` (and `ssh <ssh-user>@<lab-host>`) → `Connection timed out during banner exchange`.
  The TCP connect SUCCEEDS (port OPEN) but sshd never emits its `SSH-2.0-*` banner.
- HTTP to open ports returns `000` / empty even with `-m 8`:
  `curl -s -m 8 http://<lab-host>:11434/api/version` → nothing.
  `curl -o /dev/null -w "%{http_code}" :3000 / :5678 / :8188` → all `000`.

Interpretation: kernel + UFW accept connections, but the userspace daemons (sshd,
Docker runtime, Ollama, ComfyUI) are wedged and cannot service them.

## Fast triage sequence (run from M1/WSL, <30s total)
```bash
# 1. ping (proves kernel alive — NOT proof services are healthy)
ping -c 3 -W 2 <lab-host> | tail -4

# 2. TCP port probe (OPEN = socket held, says nothing about app health)
for p in 22 445 11434 3000 5432 5678 8188; do
  timeout 3 bash -c "cat < /dev/null > /dev/tcp/<lab-host>/$p" 2>/dev/null && echo "port $p:OPEN" || echo "port $p:closed"
done

# 3. HTTP liveness (000/empty = wedged even if port OPEN)
for s in 11434 3000 5678 8188; do
  timeout 8 curl -s -o /dev/null -w "$s:%{http_code}\n" -m 6 http://<lab-host>:$s/ 2>&1
done

# 4. SSH banner check (times out at banner = wedge; refused = sshd down; OK = healthy)
timeout 15 ssh -o BatchMode=yes -o ConnectTimeout=10 m2 "echo SHELL_OK; uptime" 2>&1 | head -3
```

## Distinguish from a CLEAN host-down
- Host fully down: ping FAILS (100% loss) AND all ports CLOSED. → just boot it.
- Wedge (this case): ping OK + ports OPEN + SSH banner-timeout + HTTP 000. → userspace hung, needs hard reboot.

## Root-cause candidates (post-reboot, check these)
1. OOM: a ComfyUI/Wan2.2 render on the dual RTX 3060s OOM-killed the container
   runtime or sshd worker. Check `sudo dmesg | grep -i 'killed process'` and
   `sudo journalctl -u ollama --since '-2h'`.
2. Hung filesystem: the NTFS `/mnt/storage` (Samba [storage] backing store) stalled,
   blocking PAM/session spawn and Docker I/O. Check `mount | grep storage` and
   `sudo dmesg | grep -i 'ntfs\|I/O error'`.
3. Maintenance-window collision: the 02:00–06:00 batch window or daily 03:00 disk
   cleanup left a process holding the box. Check `sudo journalctl --since '02:00'`.

## Recovery
- No fix possible from M1 (no shell, no API). Hard-reboot M2 via PDU / IPMI / remote KVM
  / physical power button.
- After reboot, confirm with the canonical health heredoc (`ssh m2 'bash -s' <<'EOF'`)
  from the main SKILL.md — verify GPU VRAM, Ollama tags, docker ps, disk %.

## Adjacent trap: wrong-IP ping
A successful `ping <lab-host>` does NOT mean M2 is healthy — .2 was a different LAN
device that refused 22/11434. M2 is .15, reachable ONLY via the `ssh m2` alias.
Never infer M2 health from a guessed raw IP.
