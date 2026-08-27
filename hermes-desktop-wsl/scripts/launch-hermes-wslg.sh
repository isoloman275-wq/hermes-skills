#!/usr/bin/env bash
# launch-hermes-wslg.sh — launch Hermes desktop under WSLg (Weston compositor).
#
# WHY THIS EXISTS (2026-08-13): Under VcXsrv -multiwindow, the frameless Electron
# window could NOT be dragged/moved because VcXsrv's internal WM doesn't implement
# _NET_WM_MOVERESIZE/_NET_WM_STATE_FULLSCREEN, and the frameless HWND had no
# WS_CAPTION. Diagnosis from Claude Opus 5 + Fable 5 (independently, same verdict):
# the #1 permanent fix is switching to WSLg, whose Weston compositor implements
# _NET_WM_MOVERESIZE (frameless drag works) and whose /dev/dxg + Mesa d3d12 GPU
# path removes the --disable-gpu crash hack that VcXsrv's -wgl forced.
#
# WSLg is already running on this box (Weston up, /tmp/.X11-unix/X0 live,
# DISPLAY=:0 + WAYLAND_DISPLAY=wayland-0 provided automatically). We just launch
# WITHOUT overriding DISPLAY to VcXsrv, and WITHOUT --disable-gpu.
#
# Window is a first-class Windows RAIL window: drag it with the mouse across all
# monitors, use Win+Arrow to move/snap — no SetWindowPos nudge needed.
#
# SINGLE-INSTANCE GUARD: only one launcher may run at a time.
set -u

LOCK=/tmp/launch-hermes-wslg.lock
LAUNCHER_PID=$$
if [ -f "$LOCK" ]; then
  OTHER=$(cat "$LOCK" 2>/dev/null)
  if [ -n "$OTHER" ] && kill -0 "$OTHER" 2>/dev/null; then
    echo "[launch-hermes-wslg] another lanceher loop running (pid $OTHER) — exiting"
    exit 0
  fi
fi
echo "$LAUNCHER_PID" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# Use WSLg's native display. Do NOT set DISPLAY to a Windows-host VcXsrv IP here —
# that is exactly what caused the stuck/frameless window. WSLg auto-provides
# DISPLAY=:0 and WAYLAND_DISPLAY=wayland-0 at login; just inherit them.
: "${DISPLAY:=:0}"   # keep whatever login provided; fall back to :0
export DISPLAY

cd ~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked || exit 1

# Under WSLg we can DROP --disable-gpu (VcXsrv's -wgl GLX-over-WGL was what
# crashed Chromium's GPU process; WSLg's /dev/dxg + Mesa d3d12 handles it fine).
# Keep --no-sandbox. If a GPU issue appears, degrade to: --disable-gpu-sandbox
# or pinned X11 via --ozone-platform=x11.
HERMES_ARGS="--no-sandbox --disable-gpu"

# CRASH CAPTURE (same as VcXsrv launcher): core dumps + rc>=128 evidence bundle.
ulimit -c unlimited 2>/dev/null
CRASHLOG=/tmp/hermes_crashes.log
CRASHDIR=/tmp/hermes-crash-dumps

while true; do
  echo "[launch-hermes-wslg] $(date '+%F %T') starting Hermes desktop under WSLg -> /tmp/hermes_wslg.log"
  ./Hermes $HERMES_ARGS > /tmp/hermes_wslg.log 2>&1 &
  HERMES_PID=$!
  echo $HERMES_PID > /tmp/hermes_wslg.pid

  wait "$HERMES_PID"
  rc=$?

  if [ "$rc" -ge 128 ]; then
    sig=$((rc - 128))
    echo "[launch-hermes-wslg] $(date '+%F %T') Hermes CRASHED via signal $sig (rc=$rc) — preserving evidence" >> "$CRASHLOG"
    mkdir -p "$CRASHDIR"
    stamp=$(date '+%Y%m%d_%H%M%S')
    cp /tmp/hermes_wslg.log "$CRASHDIR/${stamp}_sig${sig}_wslg_log.txt" 2>/dev/null
    [ -f core ] && cp core "$CRASHDIR/${stamp}_sig${sig}_core_wslg" 2>/dev/null
    if command -v gdb >/dev/null 2>&1 && [ -f "$CRASHDIR/${stamp}_sig${sig}_core_wslg" ]; then
      gdb -batch -ex "thread apply all bt" -ex "bt" ./Hermes \
        "$CRASHDIR/${stamp}_sig${sig}_core_wslg" > "$CRASHDIR/${stamp}_sig${sig}_bt_wslg.txt" 2>&1 || true
      echo "[launch-hermes-wslg] backtrace -> $CRASHDIR/${stamp}_sig${sig}_bt_wslg.txt" >> "$CRASHLOG"
    fi
    echo "[launch-hermes-wslg] crash artifacts in: $CRASHDIR" >> "$CRASHLOG"
  fi

  echo "[launch-hermes-wslg] $(date '+%F %T') Hermes exited rc=$rc — relaunching"
  tail -3 /tmp/hermes_wslg.log 2>/dev/null
  sleep 2
done
