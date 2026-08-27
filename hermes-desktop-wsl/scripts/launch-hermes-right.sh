#!/usr/bin/env bash
# Launch Hermes desktop and park it on a monitor. Defaults: far-right (x=1920).
# Frameless Electron under VcXsrv ignores --window-position cross-display, so we
# nudge the real Windows HWND via SetWindowPos after launch (scripts/move-hermes.ps1).
set -e
X=${1:-1920}; Y=${2:-40}; W=${3:-1000}; H=${4:-1600}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF=~/.config/Hermes/window-state.json
mkdir -p "$(dirname "$CONF")"
cat > "$CONF" <<JSON
{ "x": $X, "y": $Y, "width": $W, "height": $H, "isMaximized": false }
JSON
WINIP=$(powershell.exe -NoProfile -Command "(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress" 2>/dev/null | tr -d '\r')
: "${WINIP:=<wsl-gateway-ip>}"
export DISPLAY="$WINIP:0"
cd ~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked
./Hermes --no-sandbox --window-position=$X,$Y --window-size=$W,$H > /tmp/hermes_desktop.log 2>&1 &
HERMES_PID=$!
sleep 5
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/move-hermes.ps1" -X $X -Y $Y -W $W -H $H >/dev/null 2>&1 || true
wait "$HERMES_PID"
