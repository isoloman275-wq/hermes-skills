#!/usr/bin/env bash
# Ollama liveness watchdog — checks that a Windows-hosted Ollama instance is
# responding and relaunches it if it's gone (a silent death takes any
# dependent fleet/workers down with it — no process, nothing on :11434).
# Uses a fast /api/tags probe (catches the "server absent" failure mode).
# Safe: never pulls/deletes models, only restarts the already-installed serve.
# Edit OLLAMA_EXE and the endpoint list for your environment.
set -u
TS=$(date '+%Y-%m-%d %H:%M:%S')

# --- CONFIGURE THESE FOR YOUR SETUP ---
# URL(s) to probe. Try each in order; first that answers wins.
ENDPOINTS=("http://<lan-host-ip>:11434" "http://<wsl-gateway-ip>:11434")
# Path to the Windows ollama.exe (used only in the relaunch branch)
OLLAMA_EXE='C:\<win-user>\AppData\Local\Programs\Ollama\ollama.exe'
# ---------------------------------------

probe() {
  # $1 = base url. 0 if /api/tags returns models (server alive).
  local tags
  tags=$(timeout 10 curl -s -m8 "$1/api/tags" 2>/dev/null)
  if [ -z "$tags" ]; then return 1; fi
  if ! echo "$tags" | grep -q '"models"'; then return 1; fi
  return 0
}

UP=0
for base in "${ENDPOINTS[@]}"; do
  if probe "$base"; then UP=1; break; fi
done

if [ "$UP" = "1" ]; then
  echo "OLLAMA OK ($TS)"
  exit 0
fi

echo "OLLAMA DOWN ($TS) — no endpoint responsive, relaunching serve..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
  [Environment]::SetEnvironmentVariable('OLLAMA_HOST','0.0.0.0:11434','User');
  \$env:OLLAMA_HOST='0.0.0.0:11434';
  Start-Process -FilePath '$OLLAMA_EXE' -ArgumentList 'serve' -WindowStyle Hidden;
  Start-Sleep -Seconds 5;
  Get-Process | Where-Object { \$_.ProcessName -match 'ollama' } | Select-Object ProcessName,Id | Format-Table -AutoSize" 2>&1 | grep -v WARNING

# verify
sleep 3
if probe "${ENDPOINTS[0]}"; then
  echo "OLLAMA RECOVERED ($TS) — relaunch succeeded"
  exit 0
else
  echo "OLLAMA RECOVERY FAILED ($TS) — manual intervention needed"
  exit 1
fi