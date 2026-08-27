# Security Audit — July 2026

## M2 Findings (<lab-host> Ubuntu)

| Issue | Severity | Status |
|-------|----------|--------|
| UFW inactive — no firewall | CRITICAL | Not fixed |
| SSH password auth enabled (default) | CRITICAL | Not fixed |
| fail2ban not installed | CRITICAL | Not fixed |
| PostgreSQL 5432 on 0.0.0.0 | CRITICAL | Not fixed |
| Samba 139/445 on 0.0.0.0 | MODERATE | Not fixed |
| Unknown service port 3000 | MODERATE | Not identified |
| unattended-upgrades active | OK | — |
| No world-writable files in /home | OK | — |
| Last login from <lab-host> (M1) | OK | — |

## M3 Findings (<lab-host> Windows 10 IoT)

| Issue | Severity | Status |
|-------|----------|--------|
| Windows Firewall ON all profiles | OK | — |
| Ollama inbound rules — LAN-wide (should be M1-only) | MODERATE | Not fixed |
| RustDesk inbound rules open | MODERATE | Not fixed |
| Remote Assistance / DCOM rules enabled | MODERATE | Not fixed |
| SSDP/UPnP/mDNS/LLMNR network discovery open | LOW | Not fixed |

## M1 Findings (WSL2)

| Issue | Severity | Status |
|-------|----------|--------|
| Only port 8644 (Hermes gateway) on 0.0.0.0 | OK/MONITOR | — |

## Remediation Commands

### M2 — Enable UFW
```bash
ssh m2 'sudo ufw default deny incoming && sudo ufw default allow outgoing'
ssh m2 'sudo ufw allow from <lab-host>/24 to any port 22'
ssh m2 'sudo ufw allow from <lab-host>/24 to any port 11434'
ssh m2 'sudo ufw allow from <lab-host>/24 to any port 5678'
ssh m2 'sudo ufw allow from <lab-host>/24 to any port 8188'
ssh m2 'sudo ufw enable && sudo ufw status verbose'
```

### M2 — Harden SSH
```bash
ssh m2 'cat << EOF | sudo tee /etc/ssh/sshd_config.d/hardening.conf
PasswordAuthentication no
PermitRootLogin no
AllowUsers <ssh-user>
MaxAuthTries 3
LoginGraceTime 30
EOF'
ssh m2 'sudo systemctl reload ssh'
```

### M2 — Install fail2ban
```bash
ssh m2 'sudo apt install -y fail2ban'
ssh m2 'cat << EOF | sudo tee /etc/fail2ban/jail.local
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
EOF'
ssh m2 'sudo systemctl enable --now fail2ban'
```

### M2 — Lock PostgreSQL to localhost
```bash
ssh m2 "sudo grep listen_addresses /etc/postgresql/*/main/postgresql.conf"
# If not localhost, fix:
ssh m2 "sudo sed -i \"s/listen_addresses = '\\*'/listen_addresses = 'localhost'/\" /etc/postgresql/*/main/postgresql.conf"
ssh m2 'sudo systemctl reload postgresql'
```

### M3 — Scope Ollama to M1 IP only
```powershell
# Pipe via: cat script.ps1 | ssh m3 'powershell -Command "$input | Out-String | Invoke-Expression"'
Remove-NetFirewallRule -DisplayName "ollama" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Ollama - M1 only" `
  -Direction Inbound -Protocol TCP -LocalPort 11434 `
  -RemoteAddress <lab-host> -Action Allow
```

### M3 — Disable unnecessary inbound rules
```powershell
Disable-NetFirewallRule -DisplayName "Remote Assistance*"
Disable-NetFirewallRule -DisplayName "rustdesk*"
Disable-NetFirewallRule -Group "Network Discovery"
```

## Port Inventory (M2 as of July 2026)
| Port | Protocol | Bound | Service | Should be |
|------|----------|-------|---------|-----------|
| 22 | TCP | 0.0.0.0 | SSH | LAN only (UFW) |
| 139/445 | TCP | 0.0.0.0 | Samba | Disable if unused |
| 3000 | TCP | 0.0.0.0 | Unknown | Identify first |
| 5432 | TCP | 0.0.0.0 | PostgreSQL | localhost only |
| 5678 | TCP | 0.0.0.0 | n8n | LAN only (UFW) |
| 8188 | TCP | 0.0.0.0 | ComfyUI | LAN only (UFW) |
| 11434 | TCP | * | Ollama | LAN only (UFW) |
| 631 | TCP | 127.0.0.1 | CUPS | OK — loopback |
| 53 | UDP | 127.0.0.x | systemd-resolved | OK — loopback |
