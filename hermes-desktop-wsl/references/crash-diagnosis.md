# Hermes Desktop crash diagnosis (SIGTRAP under VcXsrv) — VERIFIED 2026-08-10

## Symptom
The Electron app "crashes again" — process gone, nothing restarted it. Recurring and
intermittent (depends on how it was launched).

## Root cause
Hard **Chromium GPU-process abort**: Chromium tries to init a GPU stack on VcXsrv and
dies with a CHECK()/abort. The GPU guards (`--disable-gpu ...`) live ONLY in the launch
args, not in `window-state.json`. A bare `./Hermes --no-sandbox` (or a launcher missing
the GPU flags) lets it SIGTRAP.

## Confirm it (the decisive evidence)
```
# 1. The actual death — absent = not this crash
dmesg | grep -i "fatal signal\|trap int3\|out of memory"
#   → "Hermes: ThreadPoolSingleThreadForeground: potentially unexpected fatal signal 5 (SIGTRAP)"
#     RIP points at a ud2 / 0f 0b trap instruction  → Chromium CHECK() abort

# 2. Rule out OOM (there is plenty here, so OOM is a red herring)
free -h

# 3. Was the GPU guard applied? If launched via the guarded launcher, /tmp/hermes_desktop.log exists
ls -la /tmp/hermes_desktop.log
#   or the app log shows:
grep -i "disabling GPU hardware acceleration" /tmp/hermes_desktop.log
```

## Benign noise — do NOT chase
`[boot] could not read served dashboard token (Hermes backend): 404: {"error":"Headless
backend (hermes serve): web UI disabled — use hermes dashboard for the browser UI."}`
The script continues to "Finalizing desktop startup" after this. It is NOT the crash.
Similarly `ERR_CONNECTION_REFUSED` on `127.0.0.1:8788` is a known dev-server quirk —
the window still renders from `file://`, so the app is usable.

## The fix: GPU-guarded + auto-restart launcher
Replaces the old `/<home>/launch-hermes-right.sh`, which (a) claimed auto-relaunch but
had NO restart loop and (b) referenced a non-existent `/tmp/fill-hermes.ps1`. The real
nudger is `<skill_dir>/scripts/move-hermes.ps1`.

```bash
#!/usr/bin/env bash
# Hermes desktop launcher — GPU-guarded + auto-restart loop.
set -u
CONF=~/.config/Hermes/window-state.json
mkdir -p "$(dirname "$CONF")"
cat > "$CONF" <<'JSON'
{ "x": 1920, "y": 0, "width": 1050, "height": 1680, "isMaximized": false }
JSON
WINIP=$(powershell.exe -NoProfile -Command "(Get-NetIPAddress -InterfaceAlias 'vEthernet*' -AddressFamily IPv4).IPAddress" 2>/dev/null | tr -d '\r')
: "${WINIP:=<wsl-gateway-ip>}"
export DISPLAY="$WINIP:0"
MOVE_PS1="$HOME/.hermes/skills/devops/hermes-desktop-wsl/scripts/move-hermes.ps1"
cd ~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked || exit 1
# GPU guards are the ONLY thing preventing the SIGTRAP crash — keep them always.
HERMES_ARGS="--no-sandbox --disable-gpu --disable-gpu-sandbox --disable-software-rasterizer --window-position=1920,0 --window-size=1050,1680"
while true; do
  echo "[launch-hermes] $(date '+%F %T') starting Hermes desktop"
  ./Hermes $HERMES_ARGS > /tmp/hermes_desktop.log 2>&1 &
  HERMES_PID=$!
  echo $HERMES_PID > /tmp/hermes_desktop.pid
  sleep 5
  [ -f "$MOVE_PS1" ] && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$MOVE_PS1" -X 1920 -Y 0 -W 1050 -H 1680 >/dev/null 2>&1 || true
  wait "$HERMES_PID"   # returns when the app exits; loop auto-relaunches
  rc=$?
  echo "[launch-hermes] $(date '+%F %T') Hermes exited rc=$rc — relaunching"
  tail -3 /tmp/hermes_desktop.log 2>/dev/null
  sleep 2
done
```

## Launch + verify
- Start as a tracked background process (NOT `nohup ... &` — Hermes rejects shell-level bg
  wrappers; use `terminal(background=true)`).
- Clean startup first: `pkill -x Hermes` may kill the calling shell too (exit -15) — re-launch
  in a fresh command after.
- Health checks after ~70s (past the earlier crash point):
  - `pgrep -x Hermes` → several PIDs (main + renderer + utility) = healthy.
  - `grep -iE "fatal|signal|crash|abort|segfault" /tmp/hermes_desktop.log` → no matches.
  - Nudge/verify window geometry on Windows: `GetWindowRect` on HWND "Hermes" =
    `1920,0 2970,1680` for the far-right 1050x1680 portrait monitor.
  - PowerShell param pitfall: passing a bare `-H` value inline can get mangled
    (`1050x4391324` / bottom=65535) — write the call to a `.ps1` file, or re-run the nudger
    with explicit ints and re-verify `GetWindowRect`.

## Key insight for future sessions
A launcher's comment is not its behavior. When a script "should" do something (auto-relaunch),
READ the loop. And when diagnosing an Electron-under-VcXsrv death, check `dmesg` FIRST — the
kernel has the ground truth; the app log's scary-looking 404 is benign.
