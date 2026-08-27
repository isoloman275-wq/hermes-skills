# Maintenance Schedule — Home Lab (NZT)

## Time Block Design
Maintenance windows are aligned to avoid inference conflicts.
ComfyUI video gen runs 02:00–06:00 NZT (GPU1 heavy). No LLM inference during this window.
All maintenance jobs slot into this window or the 06:00–08:00 quiet period.

## Cron Job Roster

| Job | Schedule (NZT) | Machine | Priority |
|-----|---------------|---------|----------|
| Lab health check | Every 6h | M1 (runs checks on all) | HIGH |
| M2 disk cleanup | Daily 03:00 | M2 via SSH | HIGH — disk at 86% |
| Hermes config backup | Daily 05:00 | M1 | HIGH |
| Security port scan | Sunday 03:00 | M1 (checks all) | MEDIUM |
| M3 Windows Defender scan | Saturday 04:00 | M3 via SSH+PS | MEDIUM |
| Audio cache cleanup | Daily 04:30 | M1 | LOW |
| Hermes session prune | Weekly Monday 05:00 | M1 | LOW |

## M2 Disk Cleanup Script
Target: keep M2 below 80% (currently 86%, critical)

```bash
ssh m2 'bash -s' << 'EOF'
echo "=== M2 Disk Cleanup $(date) ==="
df -h / | tail -1

# ComfyUI output older than 7 days
find /pipeline/comfyui_output -mtime +7 -type f -delete 2>/dev/null
echo "ComfyUI outputs pruned (>7 days)"

# Journal logs cap at 200MB
sudo journalctl --vacuum-size=200M

# Pip cache
pip cache purge 2>/dev/null || true

# Ollama model blobs (manually — don't auto-delete, just report)
du -sh ~/.ollama/models/ 2>/dev/null || du -sh /usr/share/ollama/.ollama/models/ 2>/dev/null

echo "=== After ==="
df -h / | tail -1
EOF
```

## Hermes Config Backup Script

```bash
#!/bin/bash
BACKUP_DIR=~/backups/hermes
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d)
tar -czf "$BACKUP_DIR/hermes-config-$DATE.tar.gz" \
  ~/.hermes/config.yaml \
  ~/.hermes/.env \
  ~/.hermes/skills/ \
  ~/.hermes/cron/ \
  ~/.hermes/memories/ \
  2>/dev/null
# Keep 14 days
find "$BACKUP_DIR" -name "hermes-config-*.tar.gz" -mtime +14 -delete
echo "Backup: $BACKUP_DIR/hermes-config-$DATE.tar.gz"
```

## Security Port Scan (weekly baseline check)

```bash
# Run on M2 — compare listening ports to known baseline
ssh m2 'ss -tlnp | awk "{print \$4}" | sort' > /tmp/m2-ports-current.txt
# Diff against known good (save baseline after remediation)
# diff /tmp/m2-ports-baseline.txt /tmp/m2-ports-current.txt
```

## M1 Maintenance

```bash
# Audio cache (TTS files) — older than 7 days
find ~/.hermes/audio_cache -name "*.mp3" -mtime +7 -delete

# Session prune — keep 30 days
hermes sessions prune --older-than 30

# Log rotation
find ~/.hermes/logs -name "*.log" -size +10M -exec truncate -s 5M {} \;

# Tmp cleanup
find /tmp -mtime +1 -type f -delete 2>/dev/null
```

## Alert Thresholds
| Metric | Warn | Critical | Action |
|--------|------|----------|--------|
| M2 disk | >85% | >90% | Run cleanup immediately |
| M2 GPU temp | >75°C | >85°C | Check ComfyUI batch size |
| M2 RAM available | <2GB | <500MB | Stop non-essential services |
| M1 WSL RAM | >20GB | >23GB | Check for runaway processes |
| M3 disk C: | >80% | >90% | Windows cleanup |
