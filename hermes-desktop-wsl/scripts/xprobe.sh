#!/usr/bin/env bash
# X server reachability probe that needs NO x11-utils and NO root.
#
# WHY THIS EXISTS (verified 2026-08-13):
#   The reflex check `xdpyinfo` is often NOT installed. A missing binary exits 127
#   ("No such file or directory"), which reads exactly like "X server unreachable".
#   That false negative sent a whole session chasing a Windows Firewall ghost while
#   the X server was healthy the entire time. Installing x11-utils needs sudo + an
#   interactive password an agent cannot supply, so this dependency-free probe is
#   the DEFAULT, not a fallback.
#
# HOW: X displays listen on TCP 6000 + display number (:0 -> 6000, :9 -> 6009).
#      Pure-bash /dev/tcp, no packages, no root.
#
# Usage:  xprobe.sh [host] [display]      default: <wsl-gateway-ip> :0  (port 6000)
# Exit:   0 = X server reachable, 1 = not reachable.
#
# Under WSL2 the host is the Windows vEthernet IP, NOT localhost. Find it with:
#   powershell.exe -NoProfile -Command \
#     "(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress"

HOST="${1:-<wsl-gateway-ip>}"
DISP="${2:-0}"
PORT=$((6000 + DISP))

if timeout 4 bash -c "cat < /dev/null > /dev/tcp/$HOST/$PORT" 2>/dev/null; then
  echo "X OK  - $HOST:$DISP (tcp $PORT open)"
  exit 0
else
  echo "X DOWN - $HOST:$DISP (tcp $PORT refused) -- VcXsrv not running?"
  exit 1
fi

# VALIDATE A PROBE IN BOTH DIRECTIONS before trusting it. A probe is only useful if
# it can also correctly say "down". Verified 2026-08-13:
#   ./xprobe.sh <wsl-gateway-ip> 0  -> "X OK  ... (tcp 6000 open)"      exit 0
#   ./xprobe.sh <wsl-gateway-ip> 9  -> "X DOWN ... (tcp 6009 refused)"  exit 1
# An untested probe is the same bug wearing different clothes.
#
# NOTE: VcXsrv can take a few seconds after process start before it accepts
# connections. A refused port immediately after launch is not proof of failure --
# re-probe before concluding the server is down.
